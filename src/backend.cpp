#include "backend.h"

#include <QColor>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QVariantMap>
#include <QPointer>
#include <QProcess>
#include <QSettings>
#include <QStandardPaths>
#include <QTextStream>
#include <QUuid>

#include <algorithm>
#include <cstdio>
#include <memory>

#include "filepicker.h"
#include "portalfilepicker.h"
#include "thumbprovider.h"
#include "thumbworker.h"

namespace {
constexpr int kThumbCount = 12;
constexpr int kThumbRevealMs = 70;
const QString kDefaultAccent = QStringLiteral("#FFD60A");

QString omarchyCurrentDir() {
    return QDir::homePath() + QStringLiteral("/.local/state/omarchy/current");
}

QString omarchyColorsPath() {
    return omarchyCurrentDir() + QStringLiteral("/theme/colors.toml");
}

bool isTempRoughCut(const QString &path) {
    const QFileInfo info(path);
    if (info.fileName() != QLatin1String("rough_cut.mp4"))
        return false;
    const QDir dir = info.dir();
    if (!dir.dirName().startsWith(QLatin1String("botcut-cut-")))
        return false;
    return dir.absolutePath() == QDir(QDir::temp().filePath(dir.dirName())).absolutePath();
}

QString saveFolder() {
    const QString movies = QStandardPaths::writableLocation(QStandardPaths::MoviesLocation);
    return QDir(movies).exists() ? movies : QDir::homePath();
}

QString mp4PathFor(const QString &path) {
    const QFileInfo file(path);
    if (file.suffix().compare(QStringLiteral("mp4"), Qt::CaseInsensitive) == 0)
        return path;

    const QString baseName = file.completeBaseName().isEmpty()
        ? file.fileName()
        : file.completeBaseName();
    return file.dir().filePath(baseName + QStringLiteral(".mp4"));
}

// Empty when there is no subtitle file, or the copy landed. A message when it did not.
QString captionCopyError(const QString &movieSrc, const QString &movieDst) {
    const QFileInfo srcInfo(movieSrc);
    const QString srtSrc = srcInfo.dir().filePath(QStringLiteral("rough_cut.srt"));
    if (!QFileInfo::exists(srtSrc) || !QFileInfo(srtSrc).isFile())
        return {};
    const QFileInfo dstInfo(movieDst);
    const QString srtDst = dstInfo.dir().filePath(dstInfo.completeBaseName() + QStringLiteral(".srt"));
    if (QFileInfo(srtSrc).absoluteFilePath() == QFileInfo(srtDst).absoluteFilePath())
        return {};
    QFile::remove(srtDst);
    if (!QFile::copy(srtSrc, srtDst))
        return QStringLiteral("Could not copy the captions.");
    return {};
}

bool replaceWithTemp(const QString &tmpPath, const QString &outPath) {
    const QByteArray tmpName = QFile::encodeName(tmpPath);
    const QByteArray outName = QFile::encodeName(outPath);
    return std::rename(tmpName.constData(), outName.constData()) == 0;
}

const QStringList kVideoSuffixes = {
    QStringLiteral("mp4"), QStringLiteral("mov"), QStringLiteral("mkv"),
    QStringLiteral("webm"), QStringLiteral("m4v"), QStringLiteral("avi"),
    QStringLiteral("mpeg"), QStringLiteral("mpg"),
};

bool isVideoFile(const QFileInfo &info) {
    if (!info.exists() || !info.isFile() || info.isHidden())
        return false;
    return kVideoSuffixes.contains(info.suffix(), Qt::CaseInsensitive);
}

// Earlier of birth and modified time. A copy stamps birth at the copy and
// keeps the camera's modified time, so the earlier one is when the clip was made.
QDateTime createdTime(const QFileInfo &info) {
    const QDateTime birth = info.birthTime();
    const QDateTime modified = info.lastModified();
    if (birth.isValid() && modified.isValid())
        return birth <= modified ? birth : modified;
    if (birth.isValid())
        return birth;
    return modified;
}

void sortOldestFirst(QStringList *paths) {
    std::stable_sort(paths->begin(), paths->end(), [](const QString &a, const QString &b) {
        const QFileInfo ia(a);
        const QFileInfo ib(b);
        const QDateTime ta = createdTime(ia);
        const QDateTime tb = createdTime(ib);
        if (ta.isValid() != tb.isValid())
            return ta.isValid();
        if (ta.isValid() && ta != tb)
            return ta < tb;
        return ia.fileName().compare(ib.fileName(), Qt::CaseInsensitive) < 0;
    });
}
}

Backend::Backend(ThumbProvider *provider, QObject *parent)
    : Backend(provider, new PortalFilePicker(), new LibsecretKeyStore(), true, parent) {}

Backend::Backend(ThumbProvider *provider, FilePicker *filePicker, QObject *parent)
    : Backend(provider, filePicker, new MemoryKeyStore(), true, parent) {}

Backend::Backend(ThumbProvider *provider, FilePicker *filePicker, KeyStore *keys, QObject *parent)
    : Backend(provider, filePicker, keys ? keys : new MemoryKeyStore(), keys == nullptr, parent) {}

Backend::Backend(ThumbProvider *provider, FilePicker *filePicker, KeyStore *keys, bool ownsKeys,
                 QObject *parent)
    : QObject(parent), m_provider(provider), m_filePicker(filePicker),
      m_intent(defaultCutIntent()), m_keys(keys), m_ownsKeys(ownsKeys), m_themeAccent(kDefaultAccent) {
    if (!m_filePicker->parent())
        m_filePicker->setParent(this);
    wireFilePicker();
    connect(&m_plan, &PlanFilm::committed, this, [this] {
        if (!writePlanSegments())
            setStatus(QStringLiteral("Could not save the cut"));
    });
    m_thumbRevealTimer.setInterval(kThumbRevealMs);
    connect(&m_thumbRevealTimer, &QTimer::timeout, this, &Backend::revealNextThumb);

    // Follow omarchy theme switches live. The theme lives behind a symlink that
    // gets swapped, so the reload also re-arms the watch paths every time.
    const auto themeChanged = [this] {
        watchTheme();
        loadThemeAccent();
    };
    connect(&m_themeWatcher, &QFileSystemWatcher::directoryChanged, this, themeChanged);
    connect(&m_themeWatcher, &QFileSystemWatcher::fileChanged, this, themeChanged);
    watchTheme();
    loadThemeAccent();
    if (m_keys)
        m_apiKey = m_keys->load();
    const QString stored = QSettings().value(QStringLiteral("sceneTransition"), QStringLiteral("dip")).toString();
    m_sceneTransition = stored == QLatin1String("off") ? QStringLiteral("off") : QStringLiteral("dip");
    const QString pace = QSettings().value(QStringLiteral("pace"), QStringLiteral("open")).toString();
    if (pace == QLatin1String("measured") || pace == QLatin1String("tight") || pace == QLatin1String("frenzied"))
        m_pace = pace;
}

Backend::~Backend() {
    stopTrayThumbs();
    stopThumbs();
    if (m_ownsKeys)
        delete m_keys;
}

void Backend::wireFilePicker() {
    connect(m_filePicker, &FilePicker::openSelected, this, [this](const QUrl &url) {
        // A trim dialog that was already open must not leave the shot list mid-cut.
        // Saving a finished movie still calls load() itself, while busy is set.
        if (m_busy)
            return;
        load(url);
    });
    connect(m_filePicker, &FilePicker::videosSelected, this, [this](const QList<QUrl> &urls) {
        QStringList paths;
        for (const QUrl &url : urls)
            paths.append(url.toLocalFile());
        addTrayFiles(paths);
    });
    connect(m_filePicker, &FilePicker::cutListOpenSelected, this, &Backend::loadCutListFile);
    connect(m_filePicker, &FilePicker::cutListSaveSelected, this, &Backend::writeCutListFile);
    connect(m_filePicker, &FilePicker::exportSelected, this, [this](const QUrl &url, int scaleHeight) {
        // An untouched rough cut is already the movie. Copy it. A trim still encodes.
        if (renderedUnsaved() && edit::untouched(m_timeline.clips(), m_info.duration))
            copyCut(url);
        else
            exportClips(url, m_exportDialogClips, scaleHeight);
    });
    connect(m_filePicker, &FilePicker::failed, this, &Backend::loadError);
}

void Backend::setBusy(bool busy) {
    if (m_busy == busy)
        return;
    m_busy = busy;
    emit busyChanged();
    if (busy)
        stopTrayThumbs();
    else
        scheduleTrayThumbs();
}

void Backend::setStatus(const QString &status) {
    if (m_status == status)
        return;
    m_status = status;
    emit statusChanged();
}

QString Backend::accentFromColorsFile(const QString &path, const QString &fallback) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return fallback;

    QTextStream in(&file);
    while (!in.atEnd()) {
        const QString line = in.readLine().trimmed();
        if (line.isEmpty() || line.startsWith(QLatin1Char('#')))
            continue;

        const int equals = line.indexOf(QLatin1Char('='));
        if (equals < 0 || line.left(equals).trimmed() != QStringLiteral("accent"))
            continue;

        QString value = line.mid(equals + 1).trimmed();
        if (value.size() >= 2
                && ((value.front() == QLatin1Char('"') && value.back() == QLatin1Char('"'))
                    || (value.front() == QLatin1Char('\'') && value.back() == QLatin1Char('\''))))
            value = value.mid(1, value.size() - 2);

        return QColor::fromString(value).isValid() ? value : fallback;
    }
    return fallback;
}

QString Backend::foregroundFor(const QString &color) {
    const QColor parsed = QColor::fromString(color);
    if (!parsed.isValid())
        return QStringLiteral("black");
    const double luminance = 0.299 * parsed.redF()
        + 0.587 * parsed.greenF() + 0.114 * parsed.blueF();
    return luminance < 0.5 ? QStringLiteral("white") : QStringLiteral("black");
}

QString Backend::themeAccentForeground() const {
    return foregroundFor(m_themeAccent);
}

void Backend::loadThemeAccent() {
    const QString accent = accentFromColorsFile(omarchyColorsPath(), kDefaultAccent);
    if (accent == m_themeAccent)
        return;
    m_themeAccent = accent;
    emit themeAccentChanged();
}

void Backend::watchTheme() {
    const QStringList watched = m_themeWatcher.files() + m_themeWatcher.directories();
    if (!watched.isEmpty())
        m_themeWatcher.removePaths(watched);

    const QString currentDir = omarchyCurrentDir();
    const QString themeDir = currentDir + QStringLiteral("/theme");
    if (QDir(currentDir).exists())
        m_themeWatcher.addPath(currentDir);
    if (QDir(themeDir).exists())
        m_themeWatcher.addPath(themeDir);
    if (QFileInfo::exists(omarchyColorsPath()))
        m_themeWatcher.addPath(omarchyColorsPath());
}

bool Backend::load(const QUrl &url) {
    const QString path = url.toLocalFile();
    const ffmpeg::VideoInfo info = ffmpeg::probe(path);
    if (!info.ok) {
        emit loadError(info.error);
        return false;
    }

    m_info = info;
    m_path = path;
    m_source = url;
    m_timeline.reset(m_info.duration);
    const bool wasUnsaved = renderedUnsaved();
    m_renderedHere = isTempRoughCut(path);
    m_cutSaved = false;
    if (wasUnsaved != renderedUnsaved())
        emit renderedUnsavedChanged();

    // New video: drop the old filmstrip and bump the revision so QML reloads.
    stopThumbs();
    m_thumbStart = 0.0;
    m_thumbLen = m_info.duration;
    m_fullThumbs = QVector<QImage>(kThumbCount);
    m_fullThumbsComplete = false;
    m_thumbCount = kThumbCount;
    m_thumbAvailableCount = 0;
    m_thumbReadyCount = 0;
    m_thumbWorkerDone = false;
    ++m_thumbRevision;
    m_provider->setImages(QVector<QImage>(kThumbCount));
    emit thumbsChanged();

    const bool leaveGathering = m_gathering;
    m_gathering = false;
    adoptPlanCuts();
    loadPlanFilm();
    emit infoChanged();
    if (leaveGathering)
        emit gatheringChanged();

    setStatus(QStringLiteral("Loading..."));
    startThumbs();
    return true;
}

void Backend::showShots() {
    if (m_gathering)
        return;
    m_gathering = true;
    emit gatheringChanged();
}

void Backend::showMovie() {
    if (m_source.isEmpty())
        return;
    if (!m_gathering)
        return;
    m_gathering = false;
    emit gatheringChanged();
}

bool Backend::parseKeepList(const QByteArray &json, const QString &baseDir, QString *source,
                            edit::Clips *clips, QString *error) {
    const QJsonDocument doc = QJsonDocument::fromJson(json);
    const QJsonObject root = doc.object();
    if (!doc.isObject() || !root.value("source").isString()) {
        *error = QStringLiteral("Keep-list has no source");
        return false;
    }
    const QJsonArray keep = root.value("keep").toArray();
    if (keep.isEmpty()) {
        *error = QStringLiteral("Keep-list has no ranges");
        return false;
    }
    edit::Clips parsed;
    for (int i = 0; i < keep.size(); ++i) {
        const QJsonObject r = keep.at(i).toObject();
        const double s = r.value("start").toDouble(-1), e = r.value("end").toDouble(-1);
        if (!r.value("start").isDouble() || !r.value("end").isDouble() || s < 0 || e <= s) {
            *error = QStringLiteral("Keep-list range %1 is invalid").arg(i + 1);
            return false;
        }
        parsed.append({s, e});
    }
    *source = QDir(baseDir).absoluteFilePath(root.value("source").toString());
    *clips = parsed;
    return true;
}

bool Backend::loadKeepList(const QUrl &url) {
    QFile file(url.toLocalFile());
    QString source, error;
    edit::Clips clips;
    if (!file.open(QIODevice::ReadOnly)) {
        emit loadError(QStringLiteral("Cannot read keep-list"));
        return false;
    }
    if (!parseKeepList(file.readAll(), QFileInfo(file).absolutePath(), &source, &clips, &error)) {
        emit loadError(error);
        return false;
    }
    if (!load(QUrl::fromLocalFile(source)))
        return false;
    m_timeline.load(m_info.duration, clips);
    return true;
}

void Backend::openVideoDialog() {
    if (m_busy)
        return;
    m_filePicker->openVideo();
}

void Backend::addVideosDialog() {
    if (m_busy)
        return;
    m_filePicker->openVideos();
}

void Backend::setTrayIndex(int index) {
    if (m_tray.isEmpty())
        index = -1;
    else
        index = qBound(0, index, m_tray.size() - 1);
    if (index == m_trayIndex)
        return;
    m_trayIndex = index;
    emit trayChanged();
}

QUrl Backend::previewUrl() const {
    if (m_trayIndex < 0 || m_trayIndex >= m_tray.size())
        return {};
    return QUrl::fromLocalFile(m_tray.at(m_trayIndex));
}

bool Backend::trayMissing() const {
    for (const QString &path : m_tray) {
        if (!QFileInfo(path).isFile())
            return true;
    }
    return false;
}

bool Backend::trayFileExists(const QString &path) const {
    return QFileInfo(path).isFile();
}

QString Backend::trayFileSize(const QString &path) const {
    const QFileInfo info(path);
    if (!info.isFile())
        return {};
    const qint64 bytes = info.size();
    if (bytes < 1024)
        return QString::number(bytes) + QStringLiteral(" B");
    if (bytes < 1024 * 1024)
        return QString::number((bytes + 512) / 1024) + QStringLiteral(" KB");
    if (bytes < 1024LL * 1024 * 1024)
        return QString::number((bytes + 512 * 1024) / (1024 * 1024)) + QStringLiteral(" MB");
    return QString::number(bytes / (1024.0 * 1024.0 * 1024.0), 'f', 1) + QStringLiteral(" GB");
}

bool Backend::apiKeySet() const {
    return !m_apiKey.isEmpty() || !qEnvironmentVariableIsEmpty("XAI_API_KEY");
}

void Backend::setApiKey(const QString &key) {
    const QString trimmed = key.trimmed();
    if (trimmed.isEmpty()) {
        const bool forgotten = m_keys && m_keys->forget();
        if (m_apiKey.isEmpty() && forgotten)
            return;
        m_apiKey.clear();
        emit apiKeyChanged();
        if (!forgotten)
            setStatus(QStringLiteral("Could not forget the saved key."));
        return;
    }
    const bool same = trimmed == m_apiKey;
    m_apiKey = trimmed;
    if (!same)
        emit apiKeyChanged();
    // An environment key is never written here. Only a key the user applies is.
    if (!m_keys || !m_keys->save(trimmed))
        setStatus(QStringLiteral("Could not save the key."));
}

void Backend::setIntent(const QString &intent) {
    if (m_busy)
        return;
    applyIntent(intent);
}

void Backend::applyIntent(const QString &intent) {
    if (intent == m_intent)
        return;
    m_intent = intent;
    emit intentChanged();
}

QString Backend::intentForCut() const {
    const QString trimmed = m_intent.trimmed();
    return trimmed.isEmpty() ? defaultCutIntent() : trimmed;
}

void Backend::setSceneTransition(const QString &value) {
    if (m_busy)
        return;
    applySceneTransition(value);
}

void Backend::applySceneTransition(const QString &value) {
    const QString next = value == QLatin1String("off") ? QStringLiteral("off") : QStringLiteral("dip");
    if (next == m_sceneTransition)
        return;
    m_sceneTransition = next;
    QSettings().setValue(QStringLiteral("sceneTransition"), next);
    emit sceneTransitionChanged();
}

void Backend::setPace(const QString &pace) {
    if (m_busy)
        return;
    applyPace(pace);
}

void Backend::applyPace(const QString &pace) {
    QString next = QStringLiteral("open");
    if (pace == QLatin1String("measured") || pace == QLatin1String("tight") || pace == QLatin1String("frenzied"))
        next = pace;
    if (next == m_pace)
        return;
    m_pace = next;
    QSettings().setValue(QStringLiteral("pace"), next);
    emit paceChanged();
}

void Backend::clearReviseThread() {
    m_reviseNote.clear();
    if (m_canRevert) {
        m_canRevert = false;
        emit canRevertChanged();
    }
    if (!m_reviseNotes.isEmpty()) {
        m_reviseNotes.clear();
        emit reviseNotesChanged();
    }
}

double Backend::maxPause() const {
    if (m_pace == QLatin1String("frenzied"))
        return 0.1;
    if (m_pace == QLatin1String("tight"))
        return 0.28;
    if (m_pace == QLatin1String("measured"))
        return 0.4;
    return 0.8;
}

void Backend::setCutMode(const QString &mode) {
    if (m_busy)
        return;
    if (mode != QLatin1String("speech") && mode != QLatin1String("assemble"))
        return;
    if (mode == m_cutMode)
        return;
    m_cutMode = mode;
    emit cutModeChanged();
}

void Backend::addTrayFiles(const QStringList &paths) {
    if (m_busy)
        return;
    QStringList added;
    for (const QString &path : paths) {
        const QFileInfo info(path);
        if (!info.exists() || !info.isFile())
            continue;
        const QString abs = info.absoluteFilePath();
        if (m_tray.contains(abs) || added.contains(abs))
            continue;
        added.append(abs);
    }
    if (added.isEmpty())
        return;
    sortOldestFirst(&added);
    m_tray.append(added);
    if (m_trayIndex < 0)
        m_trayIndex = 0;
    emit trayChanged();
    scheduleTrayThumbs();
}

void Backend::addDropped(const QList<QUrl> &urls) {
    if (m_busy)
        return;
    for (const QUrl &url : urls) {
        if (!url.isLocalFile())
            continue;
        const QFileInfo info(url.toLocalFile());
        if (info.isFile() && info.fileName().endsWith(QStringLiteral(".botcut.json"), Qt::CaseInsensitive)) {
            loadCutListFile(url);
            return;
        }
    }
    QStringList paths;
    for (const QUrl &url : urls) {
        if (!url.isLocalFile())
            continue;
        const QFileInfo info(url.toLocalFile());
        if (info.isDir()) {
            const QFileInfoList entries = QDir(info.absoluteFilePath())
                .entryInfoList(QDir::Files | QDir::NoDotAndDotDot | QDir::Readable, QDir::Name);
            for (const QFileInfo &entry : entries) {
                if (isVideoFile(entry))
                    paths.append(entry.absoluteFilePath());
            }
            continue;
        }
        if (isVideoFile(info))
            paths.append(info.absoluteFilePath());
    }
    addTrayFiles(paths);
}

void Backend::moveTray(int delta) {
    if (m_busy)
        return;
    const int next = m_trayIndex + delta;
    if (m_trayIndex < 0 || next < 0 || next >= m_tray.size())
        return;
    m_tray.swapItemsAt(m_trayIndex, next);
    m_trayIndex = next;
    emit trayChanged();
}

void Backend::removeTray() {
    if (m_busy)
        return;
    if (m_trayIndex < 0 || m_trayIndex >= m_tray.size())
        return;
    m_tray.removeAt(m_trayIndex);
    if (m_tray.isEmpty())
        m_trayIndex = -1;
    else if (m_trayIndex >= m_tray.size())
        m_trayIndex = m_tray.size() - 1;
    emit trayChanged();
}

namespace {
QString findTool(const QString &name) {
    const QString found = QStandardPaths::findExecutable(name);
    if (!found.isEmpty())
        return found;
    const QString local = QDir::home().filePath(QStringLiteral(".local/bin/") + name);
    return QFileInfo::exists(local) ? local : QString();
}
}

void Backend::openCutListDialog() {
    if (m_busy)
        return;
    m_filePicker->openCutList();
}

void Backend::saveCutListDialog() {
    if (m_tray.isEmpty())
        return;
    m_filePicker->saveCutList(suggestedCutListUrl());
}

QUrl Backend::suggestedCutListUrl() const {
    QString dir = QDir::homePath();
    if (!m_tray.isEmpty())
        dir = QFileInfo(m_tray.first()).absolutePath();
    return QUrl::fromLocalFile(QDir(dir).filePath(QStringLiteral("cut.botcut.json")));
}

bool Backend::loadCutListFile(const QUrl &url) {
    if (m_busy)
        return false;
    QFile file(url.toLocalFile());
    if (!file.open(QIODevice::ReadOnly)) {
        setStatus(QStringLiteral("Could not open the list"));
        return false;
    }
    QString mode;
    QString error;
    QStringList files;
    QString intent;
    QVariantList lines;
    if (!parseCutList(file.readAll(), QFileInfo(file).absolutePath(), &mode, &files, &error, &intent,
                      &lines)) {
        setStatus(error);
        return false;
    }
    m_tray = files;
    m_trayIndex = 0;
    m_selects = lines;
    m_cutOut.clear();
    clearReviseThread();
    m_listPath = QFileInfo(file).absoluteFilePath();
    emit selectsChanged();
    emit trayChanged();
    setCutMode(mode);
    setIntent(intent);
    setStatus(QString());
    rememberList(m_listPath);
    scheduleTrayThumbs();
    return true;
}

void Backend::writeCutListFile(const QUrl &url) {
    QString path = url.toLocalFile();
    if (path.isEmpty()) {
        setStatus(QStringLiteral("Could not save the list"));
        return;
    }
    if (!path.endsWith(QStringLiteral(".botcut.json"), Qt::CaseInsensitive))
        path += QStringLiteral(".botcut.json");
    const QByteArray bytes = writeCutList(m_cutMode, m_tray, intentForCut(), m_selects);
    if (bytes.isEmpty()) {
        setStatus(QStringLiteral("Could not save the list"));
        return;
    }
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        setStatus(QStringLiteral("Could not save the list"));
        return;
    }
    if (file.write(bytes) != bytes.size()) {
        setStatus(QStringLiteral("Could not save the list"));
        return;
    }
    m_listPath = QFileInfo(path).absoluteFilePath();
    rememberList(m_listPath);
    pointCutList(m_path, m_listPath);
    setStatus(QStringLiteral("Saved the list"));
}

namespace {
constexpr int kRecentCap = 6;

QString recentTitle(const QString &path) {
    const QFileInfo info(path);
    const QString name = info.fileName();
    const QString suffix = QStringLiteral(".botcut.json");
    if (name.endsWith(suffix, Qt::CaseInsensitive))
        return name.chopped(suffix.size());
    const QString base = info.completeBaseName();
    return base.isEmpty() ? name : base;
}

QJsonArray readCutArray() {
    const QString raw = QSettings().value(QStringLiteral("recentCuts")).toString();
    const QJsonDocument doc = QJsonDocument::fromJson(raw.toUtf8());
    return doc.isArray() ? doc.array() : QJsonArray();
}

void writeCutArray(const QJsonArray &cuts) {
    QSettings().setValue(QStringLiteral("recentCuts"),
                         QString::fromUtf8(QJsonDocument(cuts).toJson(QJsonDocument::Compact)));
}
}

QVariantList Backend::recentLists() const {
    QVariantList rows;
    const QStringList paths = QSettings().value(QStringLiteral("recentLists")).toStringList();
    for (const QString &path : paths) {
        QVariantMap row;
        row.insert(QStringLiteral("path"), path);
        row.insert(QStringLiteral("name"), recentTitle(path));
        rows.append(row);
    }
    return rows;
}

QVariantList Backend::recentCuts() const {
    QVariantList rows;
    const QJsonArray cuts = readCutArray();
    for (const QJsonValue &value : cuts) {
        const QJsonObject object = value.toObject();
        const QString path = object.value(QStringLiteral("path")).toString();
        if (path.isEmpty())
            continue;
        QVariantMap row;
        row.insert(QStringLiteral("path"), path);
        row.insert(QStringLiteral("name"), recentTitle(path));
        row.insert(QStringLiteral("list"), object.value(QStringLiteral("list")).toString());
        rows.append(row);
    }
    return rows;
}

void Backend::rememberList(const QString &path) {
    const QString abs = QFileInfo(path).absoluteFilePath();
    if (abs.isEmpty())
        return;
    QStringList lists = QSettings().value(QStringLiteral("recentLists")).toStringList();
    lists.removeAll(abs);
    lists.prepend(abs);
    while (lists.size() > kRecentCap)
        lists.removeLast();
    QSettings().setValue(QStringLiteral("recentLists"), lists);
    emit recentsChanged();
}

void Backend::forgetList(const QString &path) {
    const QString abs = QFileInfo(path).absoluteFilePath();
    QStringList lists = QSettings().value(QStringLiteral("recentLists")).toStringList();
    if (!lists.removeAll(abs))
        return;
    QSettings().setValue(QStringLiteral("recentLists"), lists);
    emit recentsChanged();
}

void Backend::rememberCut(const QString &movie, const QString &listPath) {
    const QString abs = QFileInfo(movie).absoluteFilePath();
    if (abs.isEmpty())
        return;
    QString cutsPath;
    if (m_planMovie == abs && !m_planCuts.isEmpty())
        cutsPath = m_planCuts;
    const QJsonArray cuts = readCutArray();
    if (cutsPath.isEmpty()) {
        for (const QJsonValue &value : cuts) {
            const QJsonObject object = value.toObject();
            if (object.value(QStringLiteral("path")).toString() == abs) {
                cutsPath = object.value(QStringLiteral("cuts")).toString();
                break;
            }
        }
    }
    QJsonArray next;
    QJsonObject row;
    row.insert(QStringLiteral("path"), abs);
    if (!listPath.isEmpty())
        row.insert(QStringLiteral("list"), QFileInfo(listPath).absoluteFilePath());
    if (!cutsPath.isEmpty())
        row.insert(QStringLiteral("cuts"), cutsPath);
    next.append(row);
    for (const QJsonValue &value : cuts) {
        if (value.toObject().value(QStringLiteral("path")).toString() == abs)
            continue;
        next.append(value);
        if (next.size() >= kRecentCap)
            break;
    }
    writeCutArray(next);
    emit recentsChanged();
}

void Backend::forgetCut(const QString &movie) {
    const QString abs = QFileInfo(movie).absoluteFilePath();
    const QJsonArray cuts = readCutArray();
    QJsonArray next;
    bool removed = false;
    for (const QJsonValue &value : cuts) {
        if (value.toObject().value(QStringLiteral("path")).toString() == abs) {
            removed = true;
            continue;
        }
        next.append(value);
    }
    if (!removed)
        return;
    writeCutArray(next);
    emit recentsChanged();
}

QString Backend::listForCurrentTray() {
    if (!m_listPath.isEmpty() && QFileInfo(m_listPath).isFile())
        return m_listPath;
    if (m_tray.isEmpty())
        return {};
    const QString base = QFileInfo(m_tray.first()).completeBaseName();
    const QString dir = QFileInfo(QSettings().fileName()).absolutePath() + QStringLiteral("/lists");
    if (!QDir().mkpath(dir))
        return {};
    const QString stem = base.isEmpty() ? QStringLiteral("cut") : base;
    QString path = QDir(dir).filePath(stem + QStringLiteral(".botcut.json"));
    if (QFileInfo::exists(path)) {
        path = QDir(dir).filePath(stem + QLatin1Char('-')
                                  + QString::number(QDateTime::currentMSecsSinceEpoch())
                                  + QStringLiteral(".botcut.json"));
    }
    const QByteArray bytes = writeCutList(m_cutMode, m_tray, intentForCut(), m_selects);
    if (bytes.isEmpty())
        return {};
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate) || file.write(bytes) != bytes.size())
        return {};
    m_listPath = QFileInfo(path).absoluteFilePath();
    rememberList(m_listPath);
    return m_listPath;
}

void Backend::rememberFinishedCut(const QString &movie) {
    rememberCut(movie, listForCurrentTray());
}

void Backend::rememberSavedCut(const QString &previous, const QString &saved) {
    if (QFileInfo(previous).absoluteFilePath() != QFileInfo(saved).absoluteFilePath())
        forgetCut(previous);
    rememberFinishedCut(saved);
}

void Backend::pointCutList(const QString &movie, const QString &listPath) {
    if (movie.isEmpty() || listPath.isEmpty())
        return;
    const QString abs = QFileInfo(movie).absoluteFilePath();
    const QString list = QFileInfo(listPath).absoluteFilePath();
    QJsonArray cuts = readCutArray();
    bool changed = false;
    for (int i = 0; i < cuts.size(); ++i) {
        QJsonObject row = cuts.at(i).toObject();
        if (row.value(QStringLiteral("path")).toString() != abs)
            continue;
        row.insert(QStringLiteral("list"), list);
        cuts[i] = row;
        changed = true;
    }
    if (!changed)
        return;
    writeCutArray(cuts);
    emit recentsChanged();
}

void Backend::reopenList(const QString &path) {
    if (m_busy)
        return;
    const QString abs = QFileInfo(path).absoluteFilePath();
    if (!QFileInfo(abs).isFile()) {
        forgetList(abs);
        setStatus(QStringLiteral("That list can't be found"));
        return;
    }
    if (!loadCutListFile(QUrl::fromLocalFile(abs)))
        return;
    showShots();
}

void Backend::watchRecent(const QString &path) {
    if (m_busy)
        return;
    const QString abs = QFileInfo(path).absoluteFilePath();
    if (!QFileInfo(abs).isFile()) {
        forgetCut(abs);
        setStatus(QStringLiteral("That movie can't be found"));
        return;
    }
    load(QUrl::fromLocalFile(abs));
}

void Backend::startCut() {
    if (m_tray.isEmpty() || m_busy)
        return;
    if (trayMissing()) {
        setStatus(QStringLiteral("A file in the list is missing"));
        return;
    }
    if (m_cutMode == QLatin1String("speech") && !apiKeySet()) {
        setStatus(QStringLiteral("Set an xAI key for spoken cuts."));
        return;
    }
    const QString cli = m_launchProgram.isEmpty() ? findTool(QStringLiteral("botcut-cli")) : m_launchProgram;
    const QString uv = m_launchProgram.isEmpty() ? findTool(QStringLiteral("uv")) : QString();
    const QString project = QDir::home().filePath(QStringLiteral("code/botcut/cli"));
    const bool projectOk = QFileInfo::exists(QDir(project).filePath(QStringLiteral("pyproject.toml")));
    const QString out = QDir::temp().filePath(
        QStringLiteral("botcut-cut-%1").arg(QDateTime::currentMSecsSinceEpoch()));
    const bool decide = m_cutMode == QLatin1String("speech");
    const CutLaunch launch = cutRunLaunch(m_tray, m_cutMode, out, cli, projectOk ? uv : QString(),
                                          projectOk ? project : QString(), intentForCut(), decide,
                                          m_sceneTransition, maxPause());
    if (!launch.error.isEmpty()) {
        setStatus(launch.error);
        return;
    }
    if (!QDir().mkpath(out)) {
        setStatus(QStringLiteral("No output directory"));
        return;
    }
    // start() returns while the process is still Starting. Keep the snapshot until started().
    m_cutOutRestore = m_cutOut;
    m_restoreCutOut = true;
    m_cutOut = out;
    setBusy(true);
    setStatus(QStringLiteral("Cutting…"));
    m_cutStage = decide ? CutStage::Decide : CutStage::Run;
    startCutProcess(launch);
}

void Backend::restoreSelect(int id) {
    if (m_busy)
        return;
    for (int i = 0; i < m_selects.size(); ++i) {
        QVariantMap row = m_selects.at(i).toMap();
        if (row.value(QStringLiteral("id")).toInt() != id || row.value(QStringLiteral("keep")).toBool())
            continue;
        row.insert(QStringLiteral("keep"), true);
        row.insert(QStringLiteral("reason"), QStringLiteral("restored"));
        m_selects[i] = row;
        emit selectsChanged();
        return;
    }
}

void Backend::dropSelect(int id) {
    if (m_busy)
        return;
    for (int i = 0; i < m_selects.size(); ++i) {
        QVariantMap row = m_selects.at(i).toMap();
        if (row.value(QStringLiteral("id")).toInt() != id || !row.value(QStringLiteral("keep")).toBool())
            continue;
        row.insert(QStringLiteral("keep"), false);
        row.insert(QStringLiteral("reason"), QStringLiteral("dropped"));
        m_selects[i] = row;
        emit selectsChanged();
        return;
    }
}

void Backend::loadSelects(const QString &cutsPath) {
    QFile file(cutsPath);
    if (!file.open(QIODevice::ReadOnly)) {
        setStatus(QStringLiteral("Could not read the selects"));
        return;
    }
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    const QJsonArray lines = doc.object().value(QStringLiteral("lines")).toArray();
    QVariantList rows;
    for (const QJsonValue &value : lines) {
        if (!value.isObject())
            continue;
        const QJsonObject line = value.toObject();
        QVariantMap row;
        row.insert(QStringLiteral("id"), line.value(QStringLiteral("id")).toInt());
        row.insert(QStringLiteral("clip"), line.value(QStringLiteral("clip")).toInt());
        row.insert(QStringLiteral("start"), line.value(QStringLiteral("start")).toDouble());
        row.insert(QStringLiteral("end"), line.value(QStringLiteral("end")).toDouble());
        row.insert(QStringLiteral("text"), line.value(QStringLiteral("text")).toString());
        row.insert(QStringLiteral("keep"), line.value(QStringLiteral("keep")).toBool());
        row.insert(QStringLiteral("reason"), line.value(QStringLiteral("reason")).toString());
        const QString still = line.value(QStringLiteral("still")).toString();
        if (!still.isEmpty()) {
            const QFileInfo stillInfo(still);
            row.insert(QStringLiteral("still"),
                       stillInfo.isRelative() ? QFileInfo(cutsPath).dir().absoluteFilePath(still)
                                              : stillInfo.absoluteFilePath());
        }
        rows.append(row);
    }
    m_selects = rows;
    emit selectsChanged();
}

namespace {
QJsonArray linesForSelects(const QVariantList &selects) {
    QJsonArray lines;
    for (const QVariant &item : selects) {
        const QVariantMap row = item.toMap();
        QJsonObject line;
        line.insert(QStringLiteral("id"), row.value(QStringLiteral("id")).toInt());
        line.insert(QStringLiteral("clip"), row.value(QStringLiteral("clip")).toInt());
        line.insert(QStringLiteral("start"), row.value(QStringLiteral("start")).toDouble());
        line.insert(QStringLiteral("end"), row.value(QStringLiteral("end")).toDouble());
        line.insert(QStringLiteral("text"), row.value(QStringLiteral("text")).toString());
        line.insert(QStringLiteral("keep"), row.value(QStringLiteral("keep")).toBool());
        line.insert(QStringLiteral("reason"), row.value(QStringLiteral("reason")).toString());
        const QString still = row.value(QStringLiteral("still")).toString();
        if (!still.isEmpty())
            line.insert(QStringLiteral("still"), still);
        lines.append(line);
    }
    return lines;
}

void shiftClipIndexes(QVariantList *rows) {
    for (int i = 0; i < rows->size(); ++i) {
        QVariantMap row = rows->at(i).toMap();
        if (!row.contains(QStringLiteral("clip")))
            continue;
        row.insert(QStringLiteral("clip"), row.value(QStringLiteral("clip")).toInt() + 1);
        (*rows)[i] = row;
    }
}

void shiftJsonClips(QJsonArray *array) {
    for (int i = 0; i < array->size(); ++i) {
        if (!array->at(i).isObject())
            continue;
        QJsonObject object = array->at(i).toObject();
        if (!object.contains(QStringLiteral("clip")))
            continue;
        object.insert(QStringLiteral("clip"), object.value(QStringLiteral("clip")).toInt() + 1);
        (*array)[i] = object;
    }
}

struct WorkShift {
    QString from;
    QString to;
};

void undoWorkShifts(const QList<WorkShift> &done) {
    for (int i = done.size() - 1; i >= 0; --i)
        QFile::rename(done.at(i).to, done.at(i).from);
}

// Captions and the next Render look up work/{index}-{stem}. Stills are named
// by line id, so that directory stays put. Highest index first, or 0-foo
// would land on the still-present 1-foo.
bool shiftWorkCaches(const QString &workDir, QList<WorkShift> *done) {
    QDir dir(workDir);
    if (!dir.exists())
        return true;
    struct Move {
        int index = 0;
        WorkShift shift;
    };
    QList<Move> moves;
    const QStringList names = dir.entryList(QDir::Files | QDir::NoDotAndDotDot);
    for (const QString &name : names) {
        if (name.isEmpty() || !name.at(0).isDigit())
            continue;
        int index = 0;
        int pos = 0;
        while (pos < name.size() && name.at(pos).isDigit()) {
            index = index * 10 + name.at(pos).digitValue();
            ++pos;
        }
        if (pos == 0 || pos >= name.size() || name.at(pos) != QLatin1Char('-'))
            continue;
        Move move;
        move.index = index;
        move.shift.from = dir.filePath(name);
        move.shift.to = dir.filePath(QString::number(index + 1) + name.mid(pos));
        moves.append(move);
    }
    std::sort(moves.begin(), moves.end(), [](const Move &a, const Move &b) { return a.index > b.index; });
    for (const Move &move : moves) {
        if (!QFile::rename(move.shift.from, move.shift.to)) {
            undoWorkShifts(*done);
            done->clear();
            return false;
        }
        done->append(move.shift);
    }
    return true;
}

// The card is a tray file, not a line, until the next spoken cut. An open card
// shifts every existing clip index so Play and Render stay on the same shots.
bool noteCardOnCuts(const QString &cutsPath, const QString &cardPath, bool open) {
    QFile file(cutsPath);
    if (!file.open(QIODevice::ReadOnly))
        return false;
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();
    if (!doc.isObject())
        return false;
    QJsonObject root = doc.object();
    if (!root.value(QStringLiteral("clips")).isArray())
        return false;
    QJsonArray clips = root.value(QStringLiteral("clips")).toArray();
    QList<WorkShift> shifted;
    if (open
        && !shiftWorkCaches(QFileInfo(cutsPath).dir().filePath(QStringLiteral("work")), &shifted))
        return false;
    QJsonObject added;
    added.insert(QStringLiteral("path"), cardPath);
    if (open) {
        QJsonArray next;
        next.append(added);
        for (const QJsonValue &value : clips)
            next.append(value);
        clips = next;
        for (const char *key : {"lines", "segments", "dropped"}) {
            const QString name = QString::fromLatin1(key);
            if (!root.value(name).isArray())
                continue;
            QJsonArray rows = root.value(name).toArray();
            shiftJsonClips(&rows);
            root.insert(name, rows);
        }
    } else {
        clips.append(added);
    }
    for (int i = 0; i < clips.size(); ++i) {
        if (!clips.at(i).isObject())
            continue;
        QJsonObject object = clips.at(i).toObject();
        object.insert(QStringLiteral("index"), i);
        clips[i] = object;
    }
    root.insert(QStringLiteral("clips"), clips);
    doc.setObject(root);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        undoWorkShifts(shifted);
        return false;
    }
    const QByteArray bytes = doc.toJson(QJsonDocument::Indented);
    if (file.write(bytes) != bytes.size()) {
        undoWorkShifts(shifted);
        return false;
    }
    return true;
}
}

bool Backend::writeSelects(const QString &cutsPath) const {
    QFile file(cutsPath);
    if (!file.open(QIODevice::ReadOnly))
        return false;
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();
    if (!doc.isObject())
        return false;
    QJsonObject root = doc.object();
    QJsonObject tighten = root.value(QStringLiteral("tighten")).toObject();
    if (!tighten.contains(QStringLiteral("snap")))
        tighten.insert(QStringLiteral("snap"), true);
    tighten.insert(QStringLiteral("max_pause"), maxPause());
    root.insert(QStringLiteral("lines"), linesForSelects(m_selects));
    root.insert(QStringLiteral("tighten"), tighten);
    // A shots-screen Render still rebuilds segments from the lines.
    root.remove(QStringLiteral("trimmed"));
    doc.setObject(root);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    const QByteArray bytes = doc.toJson(QJsonDocument::Indented);
    return file.write(bytes) == bytes.size();
}

bool Backend::writeCutsForRender(bool includeIntent) {
    const QString existing = m_cutOut.isEmpty()
                                 ? QString()
                                 : QDir(m_cutOut).filePath(QStringLiteral("cuts.json"));
    if (!existing.isEmpty() && QFileInfo::exists(existing))
        return writeSelects(existing);

    m_cutOut = QDir::temp().filePath(
        QStringLiteral("botcut-cut-%1").arg(QDateTime::currentMSecsSinceEpoch()));
    if (!QDir().mkpath(m_cutOut))
        return false;
    QJsonArray clips;
    for (int i = 0; i < m_tray.size(); ++i) {
        QJsonObject clip;
        clip.insert(QStringLiteral("index"), i);
        clip.insert(QStringLiteral("path"), m_tray.at(i));
        clips.append(clip);
    }
    QJsonObject tighten;
    tighten.insert(QStringLiteral("snap"), true);
    tighten.insert(QStringLiteral("max_pause"), maxPause());
    QJsonObject root;
    root.insert(QStringLiteral("clips"), clips);
    root.insert(QStringLiteral("lines"), linesForSelects(m_selects));
    root.insert(QStringLiteral("tighten"), tighten);
    if (includeIntent)
        root.insert(QStringLiteral("intent"), intentForCut());
    QFile file(QDir(m_cutOut).filePath(QStringLiteral("cuts.json")));
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Indented);
    return file.write(bytes) == bytes.size();
}

QString Backend::planCutsFor(const QString &movie) const {
    const QJsonArray cuts = readCutArray();
    for (const QJsonValue &value : cuts) {
        const QJsonObject object = value.toObject();
        if (object.value(QStringLiteral("path")).toString() != movie)
            continue;
        return object.value(QStringLiteral("cuts")).toString();
    }
    return {};
}

void Backend::adoptPlanCuts() {
    const QString abs = QFileInfo(m_path).absoluteFilePath();
    if (QFileInfo(m_path).fileName() == QLatin1String("rough_cut.mp4")) {
        const QString cuts = QFileInfo(m_path).dir().filePath(QStringLiteral("cuts.json"));
        if (QFileInfo(cuts).isFile()) {
            m_planCuts = QFileInfo(cuts).absoluteFilePath();
            m_planMovie = abs;
            return;
        }
    }
    const QString remembered = planCutsFor(abs);
    if (!remembered.isEmpty() && QFileInfo(remembered).isFile()) {
        m_planCuts = QFileInfo(remembered).absoluteFilePath();
        m_planMovie = abs;
        return;
    }
    m_planCuts.clear();
    m_planMovie.clear();
}

QString Backend::cutsBesideMovie() const {
    if (m_path.isEmpty())
        return {};
    const QString abs = QFileInfo(m_path).absoluteFilePath();
    if (m_planMovie == abs && !m_planCuts.isEmpty() && QFileInfo(m_planCuts).isFile())
        return m_planCuts;
    if (QFileInfo(m_path).fileName() == QLatin1String("rough_cut.mp4")) {
        const QString cuts = QFileInfo(m_path).dir().filePath(QStringLiteral("cuts.json"));
        if (QFileInfo(cuts).isFile())
            return QFileInfo(cuts).absoluteFilePath();
    }
    return {};
}

bool Backend::roughCut() const {
    return !cutsBesideMovie().isEmpty();
}

void Backend::loadPlanFilm() {
    const QString cuts = cutsBesideMovie();
    if (cuts.isEmpty()) {
        m_plan.clear();
        emit planChanged();
        return;
    }
    QFile file(cuts);
    if (!file.open(QIODevice::ReadOnly)) {
        m_plan.clear();
        emit planChanged();
        return;
    }
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    if (!doc.isObject()) {
        m_plan.clear();
        emit planChanged();
        return;
    }
    const QJsonObject root = doc.object();
    QHash<int, QJsonObject> clipsByIndex;
    for (const QJsonValue &value : root.value(QStringLiteral("clips")).toArray()) {
        if (!value.isObject())
            continue;
        const QJsonObject clip = value.toObject();
        clipsByIndex.insert(clip.value(QStringLiteral("index")).toInt(), clip);
    }
    const QString base = QFileInfo(cuts).absolutePath();
    QList<PlanFilm::Segment> segments;
    for (const QJsonValue &value : root.value(QStringLiteral("segments")).toArray()) {
        if (!value.isObject())
            continue;
        const QJsonObject obj = value.toObject();
        const int clipIndex = obj.value(QStringLiteral("clip")).toInt(-1);
        if (!clipsByIndex.contains(clipIndex))
            continue;
        const QJsonObject clip = clipsByIndex.value(clipIndex);
        QString path = clip.value(QStringLiteral("path")).toString();
        if (path.isEmpty())
            continue;
        if (QFileInfo(path).isRelative())
            path = QFileInfo(QDir(base).filePath(path)).absoluteFilePath();
        const double start = obj.value(QStringLiteral("start")).toDouble();
        const double end = obj.value(QStringLiteral("end")).toDouble();
        if (start < 0.0 || end <= start)
            continue;
        double fileDuration = clip.value(QStringLiteral("duration")).toDouble();
        if (fileDuration < end) {
            const ffmpeg::VideoInfo probed = ffmpeg::probe(path);
            if (probed.ok)
                fileDuration = std::max(fileDuration, probed.duration);
        }
        if (fileDuration < end)
            fileDuration = end;
        PlanFilm::Segment seg;
        seg.clip = clipIndex;
        seg.path = path;
        seg.fileDuration = fileDuration;
        seg.start = start;
        seg.end = end;
        seg.reason = obj.value(QStringLiteral("reason")).toString();
        seg.raw = obj;
        segments.append(seg);
    }
    if (segments.isEmpty())
        m_plan.clear();
    else
        m_plan.load(segments);
    emit planChanged();
}

bool Backend::writePlanSegments() const {
    if (!m_plan.active())
        return false;
    const QString cuts = cutsBesideMovie();
    if (cuts.isEmpty())
        return false;
    QFile file(cuts);
    if (!file.open(QIODevice::ReadOnly))
        return false;
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();
    if (!doc.isObject())
        return false;
    QJsonObject root = doc.object();
    root.insert(QStringLiteral("segments"), m_plan.segmentsJson());
    if (m_plan.unexported())
        root.insert(QStringLiteral("trimmed"), true);
    else
        root.remove(QStringLiteral("trimmed"));
    doc.setObject(root);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    const QByteArray bytes = doc.toJson(QJsonDocument::Indented);
    return file.write(bytes) == bytes.size();
}

void Backend::startBesideCut(CutStage stage, const QString &running,
                             CutLaunch (*make)(const QString &, const QString &, const QString &,
                                               const QString &)) {
    if (m_busy)
        return;
    // The cuts file already has the new ranges, but rough_cut.mp4 is still the
    // previous bake until Export. Captions and Short would cut that file.
    if (m_plan.active() && m_plan.unexported()) {
        setStatus(QStringLiteral("Export the trim first"));
        return;
    }
    const QString cuts = cutsBesideMovie();
    if (cuts.isEmpty())
        return;
    const QString cli = findTool(QStringLiteral("botcut-cli"));
    const QString uv = findTool(QStringLiteral("uv"));
    const QString project = QDir::home().filePath(QStringLiteral("code/botcut/cli"));
    const bool projectOk = QFileInfo::exists(QDir(project).filePath(QStringLiteral("pyproject.toml")));
    const CutLaunch launch = make(cuts, cli, projectOk ? uv : QString(),
                                  projectOk ? project : QString());
    if (!launch.error.isEmpty()) {
        setStatus(launch.error);
        return;
    }
    setBusy(true);
    setStatus(running);
    m_cutStage = stage;
    startCutProcess(launch);
}

void Backend::writeCaptions() {
    startBesideCut(CutStage::Captions, QStringLiteral("Writing captions"), cutCaptionsLaunch);
}

void Backend::makeShort() {
    startBesideCut(CutStage::Short, QStringLiteral("Cutting a short"), cutShortLaunch);
}

QString Backend::prepareReviseCuts() {
    const QString existing = m_cutOut.isEmpty()
                                 ? QString()
                                 : QDir(m_cutOut).filePath(QStringLiteral("cuts.json"));
    if (!existing.isEmpty() && QFileInfo::exists(existing)) {
        if (!syncLinesKeepingPause(existing))
            return {};
        return existing;
    }
    // A new file has no earlier pause to keep, so the sentence goes in this same write.
    if (!writeCutsForRender(true))
        return {};
    return QDir(m_cutOut).filePath(QStringLiteral("cuts.json"));
}

bool Backend::syncLinesKeepingPause(const QString &cutsPath) const {
    QFile file(cutsPath);
    if (!file.open(QIODevice::ReadOnly))
        return false;
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();
    if (!doc.isObject())
        return false;
    QJsonObject root = doc.object();
    root.insert(QStringLiteral("intent"), intentForCut());
    root.insert(QStringLiteral("lines"), linesForSelects(m_selects));
    // Pace lands on the next Cut or Render. This write must leave tighten alone.
    doc.setObject(root);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    const QByteArray bytes = doc.toJson(QJsonDocument::Indented);
    return file.write(bytes) == bytes.size();
}

bool Backend::readReviseOutcome(const QString &cutsPath, QString *intent, QString *pace, bool *dip,
                                QString *deliver) const {
    QFile file(cutsPath);
    if (!file.open(QIODevice::ReadOnly))
        return false;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    if (!doc.isObject())
        return false;
    const QJsonObject revise = doc.object().value(QStringLiteral("revise")).toObject();
    if (!revise.contains(QStringLiteral("pace")) || !revise.contains(QStringLiteral("dip"))
        || !revise.contains(QStringLiteral("deliver")))
        return false;
    const QString movie = doc.object().value(QStringLiteral("intent")).toString().trimmed();
    if (movie.isEmpty())
        return false;
    *intent = movie;
    *pace = revise.value(QStringLiteral("pace")).toString();
    *dip = revise.value(QStringLiteral("dip")).toBool();
    *deliver = revise.value(QStringLiteral("deliver")).toString();
    return true;
}

bool Backend::sendRevise(const QString &note) {
    if (m_busy)
        return false;
    const QString trimmed = note.simplified();
    if (trimmed.isEmpty() || m_selects.isEmpty())
        return false;
    const QString cuts = prepareReviseCuts();
    if (cuts.isEmpty()) {
        setStatus(QStringLiteral("Could not save the selects"));
        return false;
    }
    const QString cli = findTool(QStringLiteral("botcut-cli"));
    const QString uv = findTool(QStringLiteral("uv"));
    const QString project = QDir::home().filePath(QStringLiteral("code/botcut/cli"));
    const bool projectOk = QFileInfo::exists(QDir(project).filePath(QStringLiteral("pyproject.toml")));
    const CutLaunch launch = cutReviseLaunch(cuts, trimmed, cli, projectOk ? uv : QString(),
                                             projectOk ? project : QString(), m_pace, m_sceneTransition);
    if (!launch.error.isEmpty()) {
        setStatus(launch.error);
        return false;
    }
    QFile stampFile(cuts);
    if (!stampFile.open(QIODevice::ReadOnly)) {
        setStatus(QStringLiteral("Could not save the selects"));
        return false;
    }
    m_reviseStamp = stampFile.readAll();
    m_reviseNote = trimmed;
    setBusy(true);
    setStatus(QStringLiteral("Revising"));
    m_cutStage = CutStage::Revise;
    startCutProcess(launch);
    return true;
}

void Backend::revertRevise() {
    if (m_busy || !m_canRevert)
        return;
    m_canRevert = false;
    m_selects = m_undoSelects;
    emit selectsChanged();
    applyIntent(m_undoIntent);
    applyPace(m_undoPace);
    applySceneTransition(m_undoDip);
    const QString cuts = m_cutOut.isEmpty()
                             ? QString()
                             : QDir(m_cutOut).filePath(QStringLiteral("cuts.json"));
    if (!cuts.isEmpty() && QFileInfo::exists(cuts) && !syncLinesKeepingPause(cuts))
        setStatus(QStringLiteral("Could not save the selects"));
    emit canRevertChanged();
}

bool Backend::makeCard(const QString &place, const QString &sentence) {
    if (m_busy)
        return false;
    if (place != QLatin1String("open") && place != QLatin1String("close"))
        return false;
    const QString trimmed = sentence.simplified();
    if (trimmed.isEmpty())
        return false;
    QString dir;
    const QString dirError = ensureCardDirectory(&dir);
    if (!dirError.isEmpty()) {
        setStatus(dirError);
        return false;
    }
    const QString dest = QDir(dir).filePath(QStringLiteral("botcut-card-%1-%2.mp4")
                                                .arg(QUuid::createUuid().toString(QUuid::WithoutBraces), place));
    const QString cli = m_launchProgram.isEmpty() ? findTool(QStringLiteral("botcut-cli")) : m_launchProgram;
    const QString uv = m_launchProgram.isEmpty() ? findTool(QStringLiteral("uv")) : QString();
    const QString project = QDir::home().filePath(QStringLiteral("code/botcut/cli"));
    const bool projectOk = QFileInfo::exists(QDir(project).filePath(QStringLiteral("pyproject.toml")));
    const CutLaunch launch = cutCardLaunch(dest, trimmed, cli, projectOk ? uv : QString(),
                                           projectOk ? project : QString());
    if (!launch.error.isEmpty()) {
        setStatus(launch.error);
        return false;
    }
    m_cardPath = dest;
    m_cardPlace = place;
    setBusy(true);
    setStatus(QStringLiteral("Making the card…"));
    m_cutStage = CutStage::Card;
    startCutProcess(launch);
    return true;
}

void Backend::renderSelects() {
    if (m_busy || m_selects.isEmpty())
        return;
    bool anyKept = false;
    for (const QVariant &item : m_selects) {
        if (item.toMap().value(QStringLiteral("keep")).toBool()) {
            anyKept = true;
            break;
        }
    }
    if (!anyKept) {
        setStatus(QStringLiteral("Restore a line to render"));
        return;
    }
    if (!writeCutsForRender()) {
        setStatus(QStringLiteral("Could not save the selects"));
        return;
    }
    const QString cli = findTool(QStringLiteral("botcut-cli"));
    const QString uv = findTool(QStringLiteral("uv"));
    const QString project = QDir::home().filePath(QStringLiteral("code/botcut/cli"));
    const bool projectOk = QFileInfo::exists(QDir(project).filePath(QStringLiteral("pyproject.toml")));
    const CutLaunch launch = cutRenderLaunch(m_cutOut, cli, projectOk ? uv : QString(),
                                             projectOk ? project : QString(), m_sceneTransition);
    if (!launch.error.isEmpty()) {
        setStatus(launch.error);
        return;
    }
    setBusy(true);
    setStatus(QStringLiteral("Rendering 0%"));
    m_cutStage = CutStage::Render;
    startCutProcess(launch);
}

void Backend::exportPlan() {
    if (m_busy || !m_plan.active() || !m_plan.unexported())
        return;
    if (!writePlanSegments()) {
        setStatus(QStringLiteral("Could not save the cut"));
        return;
    }
    const QString cuts = cutsBesideMovie();
    if (cuts.isEmpty()) {
        setStatus(QStringLiteral("Could not save the cut"));
        return;
    }
    const QString outDir = QFileInfo(cuts).absolutePath();
    const QString cli = m_launchProgram.isEmpty() ? findTool(QStringLiteral("botcut-cli")) : m_launchProgram;
    const QString uv = m_launchProgram.isEmpty() ? findTool(QStringLiteral("uv")) : QString();
    const QString project = QDir::home().filePath(QStringLiteral("code/botcut/cli"));
    const bool projectOk = m_launchProgram.isEmpty()
                           && QFileInfo::exists(QDir(project).filePath(QStringLiteral("pyproject.toml")));
    const CutLaunch launch = cutRenderLaunch(outDir, cli, projectOk ? uv : QString(),
                                             projectOk ? project : QString(), m_sceneTransition);
    if (!launch.error.isEmpty()) {
        setStatus(launch.error);
        return;
    }
    m_cutOut = outDir;
    setBusy(true);
    setStatus(QStringLiteral("Rendering 0%"));
    m_cutStage = CutStage::Render;
    startCutProcess(launch);
}

void Backend::startCutProcess(const CutLaunch &launch) {
    if (m_cutProcess == nullptr) {
        m_cutProcess = new QProcess(this);
        m_cutProcess->setProcessChannelMode(QProcess::MergedChannels);
        connect(m_cutProcess, &QProcess::readyRead, this, &Backend::readCutOutput);
        connect(m_cutProcess, &QProcess::finished, this, &Backend::cutProcessFinished);
        connect(m_cutProcess, &QProcess::started, this, [this] {
            if (m_cutStage != CutStage::Decide && m_cutStage != CutStage::Run)
                return;
            // The revert snapshot is the only copy of the pre-revise lines.
            m_restoreCutOut = false;
            m_selects.clear();
            emit selectsChanged();
            clearReviseThread();
        });
        connect(m_cutProcess, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
            if (error != QProcess::FailedToStart)
                return;
            if (m_restoreCutOut) {
                m_cutOut = m_cutOutRestore;
                m_restoreCutOut = false;
            }
            m_cutStage = CutStage::Idle;
            m_reviseNote.clear();
            m_reviseStamp.clear();
            m_cardPath.clear();
            m_cardPlace.clear();
            setBusy(false);
            setStatus(QStringLiteral("Could not start %1").arg(m_cutProcess->program()));
        });
    }
    m_cutLog.clear();
    m_cutLine.clear();
    m_cutProcess->setProcessEnvironment(cutProcessEnvironment(QProcessEnvironment::systemEnvironment(), m_apiKey));
    m_cutProcess->start(launch.program, launch.arguments);
}

void Backend::readCutOutput() {
    if (m_cutProcess == nullptr)
        return;
    const QString chunk = QString::fromUtf8(m_cutProcess->readAll());
    if (chunk.isEmpty())
        return;
    m_cutLog += chunk;
    if (m_cutLog.size() > 4000)
        m_cutLog = m_cutLog.right(4000);
    m_cutLine += chunk;
    int newline = 0;
    while ((newline = m_cutLine.indexOf(QLatin1Char('\n'))) >= 0) {
        const QString status = cutStatusFromLine(m_cutLine.left(newline));
        m_cutLine.remove(0, newline + 1);
        // A card stays on "Making the card…" until the process exits. Retries say "Trying again".
        if (!status.isEmpty() && m_cutStage != CutStage::Card)
            setStatus(status);
    }
}

void Backend::cutProcessFinished(int code, QProcess::ExitStatus status) {
    readCutOutput();
    if (!m_cutLine.isEmpty()) {
        const QString pending = cutStatusFromLine(m_cutLine);
        if (!pending.isEmpty() && m_cutStage != CutStage::Card)
            setStatus(pending);
        m_cutLine.clear();
    }
    const auto lastLine = [this] {
        QString tail = m_cutLog.right(400).trimmed();
        const int newline = tail.lastIndexOf(QLatin1Char('\n'));
        if (newline >= 0)
            tail = tail.mid(newline + 1).trimmed();
        return tail;
    };
    if (status != QProcess::NormalExit || code != 0) {
        m_cutStage = CutStage::Idle;
        m_reviseNote.clear();
        m_reviseStamp.clear();
        m_cardPath.clear();
        m_cardPlace.clear();
        setBusy(false);
        const QString tail = lastLine();
        setStatus(tail.isEmpty() ? QStringLiteral("Cut failed") : tail);
        return;
    }
    if (m_cutStage == CutStage::Decide) {
        m_cutStage = CutStage::Idle;
        setBusy(false);
        loadSelects(QDir(m_cutOut).filePath(QStringLiteral("cuts.json")));
        return;
    }
    if (m_cutStage == CutStage::Run || m_cutStage == CutStage::Render) {
        m_cutStage = CutStage::Idle;
        setBusy(false);
        const QString cut = QDir(m_cutOut).filePath(QStringLiteral("rough_cut.mp4"));
        if (!QFileInfo::exists(cut) || !load(QUrl::fromLocalFile(cut)))
            setStatus(QStringLiteral("Could not open the cut"));
        else
            rememberFinishedCut(cut);
        return;
    }
    if (m_cutStage == CutStage::Revise) {
        m_cutStage = CutStage::Idle;
        const QString cuts = QDir(m_cutOut).filePath(QStringLiteral("cuts.json"));
        QFile written(cuts);
        const QByteArray now = written.open(QIODevice::ReadOnly) ? written.readAll() : QByteArray();
        // Exit 0 is not a revise unless this run rewrote the file. A stale object must not apply.
        const bool unchanged = now == m_reviseStamp;
        m_reviseStamp.clear();
        QString intent;
        QString pace;
        QString deliver;
        bool dip = false;
        if (unchanged || !readReviseOutcome(cuts, &intent, &pace, &dip, &deliver)) {
            m_reviseNote.clear();
            setBusy(false);
            setStatus(QStringLiteral("Could not read the revise"));
            return;
        }
        m_undoIntent = m_intent;
        m_undoPace = m_pace;
        m_undoDip = m_sceneTransition;
        m_undoSelects = m_selects;
        m_canRevert = true;
        loadSelects(cuts);
        applyIntent(intent);
        if (pace == QLatin1String("open") || pace == QLatin1String("measured")
            || pace == QLatin1String("tight") || pace == QLatin1String("frenzied"))
            applyPace(pace);
        applySceneTransition(dip ? QStringLiteral("dip") : QStringLiteral("off"));
        if (!m_reviseNote.isEmpty()) {
            m_reviseNotes.append(m_reviseNote);
            m_reviseNote.clear();
            while (m_reviseNotes.size() > 3)
                m_reviseNotes.removeFirst();
            emit reviseNotesChanged();
        }
        emit canRevertChanged();
        setBusy(false);
        if (deliver == QLatin1String("render"))
            setStatus(QStringLiteral("Ready to render"));
        else if (deliver == QLatin1String("captions"))
            setStatus(QStringLiteral("Ready for captions"));
        else if (deliver == QLatin1String("short"))
            setStatus(QStringLiteral("Ready for a short"));
        return;
    }
    if (m_cutStage == CutStage::Card) {
        const QString path = m_cardPath;
        const QString place = m_cardPlace;
        m_cardPath.clear();
        m_cardPlace.clear();
        m_cutStage = CutStage::Idle;
        const QFileInfo info(path);
        const QString abs = info.absoluteFilePath();
        if (info.isSymbolicLink() || !info.isFile() || info.size() <= 0
            || !cardDestinationError(abs).isEmpty()) {
            setBusy(false);
            setStatus(QStringLiteral("Could not make the card"));
            return;
        }
        if (!m_tray.contains(abs)) {
            const bool open = place != QLatin1String("close");
            if (!open) {
                m_tray.append(abs);
                if (m_trayIndex < 0)
                    m_trayIndex = 0;
            } else {
                m_tray.prepend(abs);
                m_trayIndex = m_trayIndex < 0 ? 0 : m_trayIndex + 1;
                shiftClipIndexes(&m_selects);
                shiftClipIndexes(&m_undoSelects);
                if (!m_selects.isEmpty())
                    emit selectsChanged();
            }
            emit trayChanged();
            const QString cuts = m_cutOut.isEmpty()
                                     ? QString()
                                     : QDir(m_cutOut).filePath(QStringLiteral("cuts.json"));
            if (!cuts.isEmpty() && QFileInfo::exists(cuts) && !noteCardOnCuts(cuts, abs, open)) {
                setBusy(false);
                setStatus(QStringLiteral("Could not save the selects"));
                return;
            }
        }
        setBusy(false);
        setStatus(QString());
        return;
    }
    if (m_cutStage == CutStage::Captions || m_cutStage == CutStage::Short) {
        const bool captions = m_cutStage == CutStage::Captions;
        m_cutStage = CutStage::Idle;
        setBusy(false);
        const QString side = QDir(QFileInfo(m_path).absolutePath())
                                 .filePath(captions ? QStringLiteral("rough_cut.srt")
                                                    : QStringLiteral("short.mp4"));
        if (QFileInfo::exists(side) && QFileInfo(side).isFile()) {
            setStatus(captions ? QStringLiteral("Wrote the captions")
                               : QStringLiteral("Wrote the short"));
            return;
        }
        const QString tail = lastLine();
        setStatus(tail.isEmpty()
                      ? (captions ? QStringLiteral("Could not write the captions")
                                  : QStringLiteral("Could not write the short"))
                      : tail);
        return;
    }
    m_cutStage = CutStage::Idle;
    setBusy(false);
    setStatus(QString());
}

void Backend::exportDialog() {
    if (m_busy || m_path.isEmpty() || !m_info.ok)
        return;

    m_exportDialogClips = m_timeline.clips();
    m_filePicker->exportVideo(suggestedExportUrl(), exportHeights(m_info.width, m_info.height));
}

QList<int> Backend::exportHeights(int width, int height) {
    const int shortSide = qMin(width, height);
    QList<int> heights;
    for (const int candidate : {1080, 720}) {
        if (shortSide > candidate)
            heights << candidate;
    }
    return heights;
}

namespace {
qint64 shotMtimeMs(const QFileInfo &info) {
    return info.lastModified().toMSecsSinceEpoch();
}

QString shotThumbFile(const QFileInfo &info) {
    const QString token = info.absoluteFilePath() + QLatin1Char('|') + QString::number(info.size())
                          + QLatin1Char('|') + QString::number(shotMtimeMs(info));
    const QByteArray hex = QCryptographicHash::hash(token.toUtf8(), QCryptographicHash::Sha1).toHex();
    const QString dir = QStandardPaths::writableLocation(QStandardPaths::CacheLocation)
                        + QStringLiteral("/shots");
    return dir + QLatin1Char('/') + QString::fromLatin1(hex.left(20)) + QStringLiteral(".jpg");
}

}

bool Backend::trayThumbFresh(const TrayThumbEntry &entry, const QFileInfo &info) {
    if (entry.size != info.size() || entry.mtimeMs != shotMtimeMs(info))
        return false;
    if (entry.file.isEmpty())
        return true;
    const QFileInfo jpeg(entry.file);
    return jpeg.isFile() && jpeg.size() > 0;
}

QString Backend::trayThumb(const QString &path) const {
    const QFileInfo info(path);
    const auto it = m_trayThumbs.constFind(info.absoluteFilePath());
    if (it == m_trayThumbs.cend() || !trayThumbFresh(*it, info) || it->file.isEmpty())
        return {};
    return it->file;
}

bool Backend::trayThumbPending(const QString &path) const {
    const QFileInfo info(path);
    if (!info.isFile())
        return false;
    const auto it = m_trayThumbs.constFind(info.absoluteFilePath());
    return it == m_trayThumbs.cend() || !trayThumbFresh(*it, info);
}

void Backend::stopTrayThumbs() {
    if (!m_trayThumbWorker)
        return;
    TrayThumbWorker *worker = m_trayThumbWorker;
    m_trayThumbWorker = nullptr;
    worker->disconnect(this);
    worker->requestStop();
    worker->wait();
    delete worker;
}

void Backend::scheduleTrayThumbs() {
    if (m_busy || m_trayThumbWorker)
        return;
    bool adopted = false;
    for (const QString &path : m_tray) {
        const QFileInfo info(path);
        if (!info.isFile())
            continue;
        const QString abs = info.absoluteFilePath();
        const auto known = m_trayThumbs.constFind(abs);
        if (known != m_trayThumbs.cend() && trayThumbFresh(*known, info))
            continue;
        const QString jpeg = shotThumbFile(info);
        if (QFileInfo(jpeg).isFile() && QFileInfo(jpeg).size() > 0) {
            m_trayThumbs.insert(abs, TrayThumbEntry{info.size(), shotMtimeMs(info), jpeg});
            adopted = true;
            continue;
        }
        if (adopted) {
            ++m_trayThumbRevision;
            emit trayThumbsChanged();
        }
        const qint64 size = info.size();
        const qint64 mtime = shotMtimeMs(info);
        auto *worker = new TrayThumbWorker(abs, this);
        m_trayThumbWorker = worker;
        const QPointer<TrayThumbWorker> guard(worker);
        connect(worker, &TrayThumbWorker::grabbed, this,
                [this, guard, jpeg, size, mtime](const QString &shot, const QImage &image) {
            if (!guard || guard != m_trayThumbWorker || image.isNull())
                return;
            QDir().mkpath(QFileInfo(jpeg).absolutePath());
            if (!image.save(jpeg, "JPEG", 80)) {
                m_trayThumbs.insert(shot, TrayThumbEntry{size, mtime, {}});
                return;
            }
            m_trayThumbs.insert(shot, TrayThumbEntry{size, mtime, jpeg});
            ++m_trayThumbRevision;
            emit trayThumbsChanged();
        });
        connect(worker, &TrayThumbWorker::finished, this, [this, guard, abs, size, mtime] {
            // A stop() deletes the worker. A queued callback then sees a null
            // guard and leaves the path uncached, so the next idle pass retries.
            if (!guard)
                return;
            const bool current = guard == m_trayThumbWorker;
            if (current)
                m_trayThumbWorker = nullptr;
            const auto known = m_trayThumbs.constFind(abs);
            const bool stored = known != m_trayThumbs.cend() && known->size == size && known->mtimeMs == mtime;
            if (current && !stored) {
                // Remember the miss for this size and time only. It is not written to disk.
                m_trayThumbs.insert(abs, TrayThumbEntry{size, mtime, {}});
                ++m_trayThumbRevision;
                emit trayThumbsChanged();
            }
            guard->deleteLater();
            if (current)
                scheduleTrayThumbs();
        });
        worker->start();
        return;
    }
    if (adopted) {
        ++m_trayThumbRevision;
        emit trayThumbsChanged();
    }
}

void Backend::startThumbs() {
    auto *worker = new ThumbWorker(m_path, m_thumbStart, m_thumbLen, kThumbCount);
    m_thumbWorker = worker;
    // Pair the pointer check with the revision: a recycled worker address could
    // otherwise let a stale queued callback write into the new filmstrip.
    const int revision = m_thumbRevision;

    connect(worker, &ThumbWorker::thumbReady, this, [this, worker, revision](int index, const QImage &image) {
        if (worker != m_thumbWorker || revision != m_thumbRevision)
            return;
        m_provider->setImage(index, image);
        // Thumbs arrive in order, so the strip is fully cached at the last one.
        if (m_thumbStart <= 0.0 && m_thumbLen >= m_info.duration) {
            m_fullThumbs[index] = image;
            if (index == kThumbCount - 1)
                m_fullThumbsComplete = true;
        }
        m_thumbAvailableCount = qMax(m_thumbAvailableCount, index + 1);
        if (m_thumbReadyCount == 0)
            revealNextThumb();
        if (!m_thumbRevealTimer.isActive())
            m_thumbRevealTimer.start();
    });
    connect(worker, &ThumbWorker::finished, this, [this, worker, revision] {
        if (worker == m_thumbWorker && revision == m_thumbRevision) {
            m_thumbWorker = nullptr;
            m_thumbWorkerDone = true;
            if (m_thumbReadyCount >= m_thumbCount && m_status == QLatin1String("Loading..."))
                setStatus(QString());
            else if (!m_thumbRevealTimer.isActive())
                m_thumbRevealTimer.start();
        }
        worker->deleteLater();
    });
    worker->start();
}

void Backend::revealNextThumb() {
    if (m_thumbReadyCount < m_thumbAvailableCount) {
        ++m_thumbReadyCount;
        emit thumbsChanged();
    }

    if (m_thumbReadyCount < m_thumbAvailableCount)
        return;

    m_thumbRevealTimer.stop();
    if (m_thumbWorkerDone && m_thumbReadyCount >= m_thumbCount
            && m_status == QLatin1String("Loading..."))
        setStatus(QString());
}

void Backend::stopThumbs() {
    m_thumbRevealTimer.stop();
    if (!m_thumbWorker)
        return;

    ThumbWorker *worker = m_thumbWorker;
    m_thumbWorker = nullptr;
    worker->disconnect(this);
    worker->requestStop();
    worker->wait();
    delete worker;
}

void Backend::requestThumbs(double start, double end) {
    if (m_path.isEmpty() || !m_info.ok)
        return;
    start = qBound(0.0, start, m_info.duration);
    end = qBound(start, end, m_info.duration);
    if (end - start <= 0.0 || (start == m_thumbStart && end - start == m_thumbLen))
        return;

    stopThumbs();
    m_thumbStart = start;
    m_thumbLen = end - start;
    ++m_thumbRevision;

    // Zooming back out: restore the cached full-length strip instantly.
    if (start <= 0.0 && end >= m_info.duration && m_fullThumbsComplete) {
        m_provider->setImages(m_fullThumbs);
        m_thumbAvailableCount = kThumbCount;
        m_thumbReadyCount = kThumbCount;
        m_thumbWorkerDone = true;
        emit thumbsChanged();
        return;
    }

    m_thumbAvailableCount = 0;
    m_thumbReadyCount = 0;
    m_thumbWorkerDone = false;
    m_provider->setImages(QVector<QImage>(kThumbCount));
    emit thumbsChanged();
    startThumbs();
}

QUrl Backend::suggestedExportUrl() const {
    if (m_path.isEmpty())
        return {};
    const QFileInfo src(m_path);
    // The portal will not open a save dialog whose folder is /tmp, which is
    // where a fresh rough cut lives. Offer a folder the user can write.
    if (m_renderedHere) {
        QString name = src.completeBaseName() + QStringLiteral("_trimmed.mp4");
        if (edit::untouched(m_timeline.clips(), m_info.duration)) {
            name = m_tray.isEmpty() ? QStringLiteral("cut.mp4")
                                    : QFileInfo(m_tray.first()).completeBaseName() + QStringLiteral(".mp4");
        }
        return QUrl::fromLocalFile(QDir(saveFolder()).filePath(name));
    }
    return QUrl::fromLocalFile(src.dir().filePath(src.completeBaseName() + QStringLiteral("_trimmed.mp4")));
}

void Backend::copyCut(const QUrl &dst) {
    if (m_path.isEmpty() || !m_info.ok || m_busy)
        return;
    const QString selectedPath = dst.toLocalFile();
    const QString outPath = mp4PathFor(selectedPath);
    if (outPath != selectedPath && QFileInfo::exists(outPath)) {
        emit exportFailed(QStringLiteral("%1 already exists.").arg(QFileInfo(outPath).fileName()));
        return;
    }
    if (QFileInfo(outPath).absoluteFilePath() == QFileInfo(m_path).absoluteFilePath()) {
        rememberSavedCut(m_path, outPath);
        noteCutSaved(outPath);
        return;
    }
    const QString cp = QStandardPaths::findExecutable(QStringLiteral("cp"));
    if (cp.isEmpty()) {
        emit exportFailed(QStringLiteral("Could not save the movie."));
        return;
    }
    setBusy(true);
    setStatus(QStringLiteral("Saving…"));
    auto *proc = new QProcess(this);
    auto completed = std::make_shared<bool>(false);
    connect(proc, &QProcess::finished, this, [this, proc, outPath, completed](int code, QProcess::ExitStatus exitStatus) {
        if (*completed)
            return;
        *completed = true;
        const QString err = QString::fromUtf8(proc->readAllStandardError()).trimmed();
        proc->deleteLater();
        if (exitStatus != QProcess::NormalExit || code != 0) {
            setBusy(false);
            setStatus(QString());
            emit exportFailed(err.isEmpty() ? QStringLiteral("Could not save the movie.") : err);
            return;
        }
        const QString source = m_path;
        const QString plan = cutsBesideMovie();
        const QString captionNote = captionCopyError(m_path, outPath);
        if (!load(QUrl::fromLocalFile(outPath))) {
            setBusy(false);
            setStatus(QStringLiteral("Could not open the cut"));
            emit exportFailed(QStringLiteral("Could not open the cut"));
            return;
        }
        if (!plan.isEmpty()) {
            m_planCuts = plan;
            m_planMovie = QFileInfo(outPath).absoluteFilePath();
            // load() cleared the film because the saved name is not rough_cut.mp4.
            loadPlanFilm();
            emit infoChanged();
        }
        rememberSavedCut(source, outPath);
        noteCutSaved(outPath);
        if (!captionNote.isEmpty())
            setStatus(captionNote);
    });
    connect(proc, &QProcess::errorOccurred, this, [this, proc, completed](QProcess::ProcessError error) {
        if (error != QProcess::FailedToStart || *completed)
            return;
        *completed = true;
        const QString err = proc->errorString();
        proc->deleteLater();
        setBusy(false);
        setStatus(QString());
        emit exportFailed(err.isEmpty() ? QStringLiteral("Could not save the movie.") : err);
    });
    proc->start(cp, {QStringLiteral("-f"), m_path, outPath});
}

void Backend::noteCutSaved(const QString &path) {
    m_cutSaved = true;
    setBusy(false);
    setStatus(QString());
    emit renderedUnsavedChanged();
    emit exportDone(path);
}

void Backend::exportClips(const QUrl &dst, const edit::Clips &clips, int scaleHeight) {
    if (m_path.isEmpty() || !m_info.ok || m_busy)
        return;

    const QList<edit::Range> ranges = edit::kept(clips);
    const double clipLen = edit::keptDuration(clips);
    if (clipLen <= 0.0) {
        emit exportFailed("The selected clip has no length.");
        return;
    }

    // Forcing the .mp4 suffix can redirect the write to a file the save
    // dialog never asked the user about overwriting — refuse rather than
    // silently replace it.
    const QString selectedPath = dst.toLocalFile();
    const QString outPath = mp4PathFor(selectedPath);
    if (outPath != selectedPath && QFileInfo::exists(outPath)) {
        emit exportFailed(QStringLiteral("%1 already exists.")
                              .arg(QFileInfo(outPath).fileName()));
        return;
    }

    const QString ffmpegBin = ffmpeg::toolPath("ffmpeg");
    if (ffmpegBin.isEmpty()) {
        emit exportFailed("`ffmpeg` was not found on your PATH.");
        return;
    }

    QString deviceError;
    const QString device = ffmpeg::vaapiDevice(&deviceError);
    if (!deviceError.isEmpty()) {
        emit exportFailed(deviceError);
        return;
    }

    setBusy(true);
    setStatus(QStringLiteral("Exporting 0%"));

    // Encode to a sibling temp file and atomically replace the target only after
    // success, so failed/cancelled exports preserve any existing file.
    const QString tmpPath = outPath + QStringLiteral(".botcut-part.mp4");
    QFile::remove(tmpPath);
    const QStringList args = ffmpeg::trimArgs(m_path, tmpPath, ranges, m_info.audio, scaleHeight, device,
                                              m_info.width, m_info.height, m_info.rotation, m_info.frameRate);

    auto *proc = new QProcess(this);
    auto completed = std::make_shared<bool>(false);

    // ffmpeg -progress writes key=value blocks to stdout as it encodes;
    // out_time_us against the kept length gives the percentage.
    auto progressBuf = std::make_shared<QByteArray>();
    connect(proc, &QProcess::readyReadStandardOutput, this,
            [this, proc, progressBuf, clipLen, completed] {
                progressBuf->append(proc->readAllStandardOutput());
                int newline;
                while ((newline = progressBuf->indexOf('\n')) >= 0) {
                    const QByteArray line = progressBuf->left(newline).trimmed();
                    progressBuf->remove(0, newline + 1);
                    if (*completed || !line.startsWith("out_time_us="))
                        continue;
                    bool ok = false;
                    const double outSecs = line.mid(line.indexOf('=') + 1).toLongLong(&ok) / 1e6;
                    if (!ok)
                        continue;
                    const int percent = qBound(0, qRound(outSecs / clipLen * 100.0), 100);
                    setStatus(QStringLiteral("Exporting %1%").arg(percent));
                }
            });

    connect(proc, &QProcess::finished, this,
            [this, proc, outPath, tmpPath, completed, clips](int code, QProcess::ExitStatus exitStatus) {
                if (*completed)
                    return;
                *completed = true;
                const QString err = QString::fromUtf8(proc->readAllStandardError()).trimmed();
                proc->deleteLater();
                if (exitStatus != QProcess::NormalExit || code != 0) {
                    failExport(tmpPath, err.isEmpty() ? QStringLiteral("ffmpeg trim failed.") : err);
                    return;
                }
                if (!replaceWithTemp(tmpPath, outPath)) {
                    failExport(tmpPath, QStringLiteral("Could not write the exported file."));
                    return;
                }
                setBusy(false);
                setStatus(QString());
                m_timeline.markExported(clips);
                if (m_renderedHere && !m_cutSaved) {
                    m_cutSaved = true;
                    emit renderedUnsavedChanged();
                }
                emit exportDone(outPath);
            });
    connect(proc, &QProcess::errorOccurred, this,
            [this, proc, tmpPath, completed](QProcess::ProcessError error) {
                if (error != QProcess::FailedToStart || *completed)
                    return;
                *completed = true;
                const QString err = proc->errorString();
                proc->deleteLater();
                failExport(tmpPath, err.isEmpty() ? QStringLiteral("Could not start ffmpeg.") : err);
            });
    proc->start(ffmpegBin, args);
}

void Backend::failExport(const QString &tmpPath, const QString &message) {
    setBusy(false);
    setStatus(QString());
    QFile::remove(tmpPath);
    emit exportFailed(message);
}
