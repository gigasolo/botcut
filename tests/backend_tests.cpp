#include <QtTest>

#include <QDateTime>
#include <QDir>
#include <QElapsedTimer>
#include <QTimeZone>
#include <QFile>
#include <QFileInfo>
#include <QProcess>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSettings>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QVariantList>

#include "backend.h"
#include "filepicker.h"
#include "thumbprovider.h"
#include "cutjob.h"
#include "thumbworker.h"

class FakeFilePicker : public FilePicker {
    Q_OBJECT

public:
    int openCount = 0;
    int exportCount = 0;
    QUrl lastSuggestedUrl;
    QList<int> lastScaleHeights;

    void openVideo() override { ++openCount; }
    void openVideos() override { ++openCount; }
    void openCutList() override {}
    void saveCutList(const QUrl &) override {}

    void exportVideo(const QUrl &suggestedUrl, const QList<int> &scaleHeights) override {
        ++exportCount;
        lastSuggestedUrl = suggestedUrl;
        lastScaleHeights = scaleHeights;
    }
};

class EnvVarGuard {
public:
    explicit EnvVarGuard(const char *name)
        : m_name(name), m_oldValue(qgetenv(name)), m_hadValue(qEnvironmentVariableIsSet(name)) {}

    ~EnvVarGuard() {
        if (m_hadValue)
            qputenv(m_name.constData(), m_oldValue);
        else
            qunsetenv(m_name.constData());
    }

private:
    QByteArray m_name;
    QByteArray m_oldValue;
    bool m_hadValue;
};

class ShortcutBackend : public QObject {
    Q_OBJECT
    Q_PROPERTY(QUrl source READ source NOTIFY infoChanged)
    Q_PROPERTY(double duration READ duration NOTIFY infoChanged)
    Q_PROPERTY(int thumbCount READ thumbCount NOTIFY thumbsChanged)
    Q_PROPERTY(int thumbReadyCount READ thumbReadyCount NOTIFY thumbsChanged)
    Q_PROPERTY(int thumbRevision READ thumbRevision NOTIFY thumbsChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString themeAccent READ themeAccent NOTIFY themeAccentChanged)
    Q_PROPERTY(QString themeAccentForeground READ themeAccentForeground NOTIFY themeAccentChanged)
    Q_PROPERTY(QObject *timeline READ timelineObject CONSTANT)

public:
    explicit ShortcutBackend(QUrl source, double duration, QObject *parent = nullptr)
        : QObject(parent), m_source(std::move(source)), m_duration(duration) {
        timeline.reset(duration);
    }

    QUrl source() const { return m_source; }
    double duration() const { return m_duration; }
    int thumbCount() const { return 0; }
    int thumbReadyCount() const { return 0; }
    int thumbRevision() const { return 0; }
    bool busy() const { return false; }
    QString status() const { return {}; }
    QString themeAccent() const { return QStringLiteral("#FFD60A"); }
    QString themeAccentForeground() const { return QStringLiteral("black"); }
    QObject *timelineObject() { return &timeline; }

    Q_INVOKABLE bool load(const QUrl &) { return false; }
    Q_INVOKABLE void openVideoDialog() { ++openCount; }
    Q_PROPERTY(QStringList tray READ tray NOTIFY infoChanged)
    Q_PROPERTY(int trayIndex READ trayIndex WRITE setTrayIndex NOTIFY infoChanged)
    Q_PROPERTY(QString cutMode READ cutMode WRITE setCutMode NOTIFY infoChanged)
    Q_PROPERTY(bool gathering READ gathering NOTIFY infoChanged)
    Q_PROPERTY(QUrl previewUrl READ previewUrl NOTIFY infoChanged)
    Q_PROPERTY(bool trayMissing READ trayMissing NOTIFY infoChanged)
    Q_PROPERTY(int trayThumbRevision READ trayThumbRevision NOTIFY infoChanged)
    Q_PROPERTY(bool apiKeySet READ apiKeySet NOTIFY infoChanged)
    Q_PROPERTY(bool renderedUnsaved READ renderedUnsaved NOTIFY infoChanged)
    Q_PROPERTY(bool roughCut READ roughCut NOTIFY infoChanged)
    Q_PROPERTY(QString intent READ intent WRITE setIntent NOTIFY infoChanged)
    Q_PROPERTY(QString sceneTransition READ sceneTransition WRITE setSceneTransition NOTIFY infoChanged)
    Q_PROPERTY(QVariantList selects READ selects NOTIFY infoChanged)
    void setTray(const QStringList &tray) { m_tray = tray; }
    void setSelects(const QVariantList &selects) { m_selects = selects; }
    QStringList tray() const { return m_tray; }
    int trayIndex() const { return -1; }
    void setTrayIndex(int) {}
    QString cutMode() const { return m_cutMode; }
    void setCutMode(const QString &mode) {
        if (mode != QLatin1String("speech") && mode != QLatin1String("assemble"))
            return;
        if (mode == m_cutMode)
            return;
        m_cutMode = mode;
        emit infoChanged();
    }
    bool gathering() const { return m_source.isEmpty(); }
    QUrl previewUrl() const { return {}; }
    bool trayMissing() const { return false; }
    int trayThumbRevision() const { return 0; }
    bool apiKeySet() const { return false; }
    bool renderedUnsaved() const { return m_renderedUnsaved; }
    bool roughCut() const { return false; }
    void setRenderedUnsaved(bool value) { m_renderedUnsaved = value; }
    QString intent() const { return defaultCutIntent(); }
    void setIntent(const QString &) {}
    QString sceneTransition() const { return m_sceneTransition; }
    void setSceneTransition(const QString &value) {
        m_sceneTransition = value == QLatin1String("off") ? QStringLiteral("off") : QStringLiteral("dip");
    }
    QVariantList selects() const { return m_selects; }
    Q_INVOKABLE void restoreSelect(int) {}
    Q_INVOKABLE void renderSelects() {}
    Q_INVOKABLE void writeCaptions() {}
    Q_INVOKABLE void makeShort() {}
    Q_INVOKABLE void addVideosDialog() {}
    Q_INVOKABLE void addDropped(const QList<QUrl> &) {}
    Q_INVOKABLE bool trayFileExists(const QString &) const { return true; }
    Q_INVOKABLE QString trayFileSize(const QString &) const { return QStringLiteral("1 MB"); }
    Q_INVOKABLE QString trayThumb(const QString &) const { return {}; }
    Q_INVOKABLE bool trayThumbPending(const QString &) const { return false; }
    Q_INVOKABLE void openCutListDialog() {}
    Q_INVOKABLE void saveCutListDialog() {}
    Q_INVOKABLE void setApiKey(const QString &) {}
    Q_INVOKABLE void moveTray(int) {}
    Q_INVOKABLE void removeTray() {}
    Q_INVOKABLE void startCut() {}
    Q_INVOKABLE void exportDialog() {
        ++exportCount;
        exportedClips = timeline.clips();
    }
    Q_INVOKABLE QUrl suggestedExportUrl() const { return {}; }
    Q_INVOKABLE void requestThumbs(double start, double end) {
        ++thumbRequestCount;
        lastThumbStart = start;
        lastThumbEnd = end;
    }
    Q_INVOKABLE void showShots() {}
    Q_INVOKABLE void showMovie() {}

    void announceInfo() {
        timeline.reset(m_duration);
        emit infoChanged();
    }
    void announceExportDone() {
        timeline.markExported(exportedClips);
        emit exportDone(QStringLiteral("/tmp/exported.mp4"));
    }

    Timeline timeline;
    edit::Clips exportedClips;
    QString m_cutMode = QStringLiteral("speech");
    int openCount = 0;
    int exportCount = 0;
    int thumbRequestCount = 0;
    double lastThumbStart = 0;
    double lastThumbEnd = 0;

signals:
    void infoChanged();
    void thumbsChanged();
    void busyChanged();
    void statusChanged();
    void themeAccentChanged();
    void exportDone(const QString &path);
    void exportFailed(const QString &message);
    void loadError(const QString &message);

private:
    QUrl m_source;
    double m_duration;
    QStringList m_tray;
    QVariantList m_selects;
    bool m_renderedUnsaved = false;
    QString m_sceneTransition = QStringLiteral("dip");
};

// Finds a DialogButton by its label ("primary" tells them apart from Labels).
static QQuickItem *dialogButton(QQuickWindow *window, const QString &text) {
    const auto items = window->findChildren<QQuickItem *>();
    for (QQuickItem *item : items) {
        if (item->property("primary").isValid() && item->property("text").toString() == text)
            return item;
    }
    return nullptr;
}

static QPoint itemCenter(QQuickItem *item) {
    return item->mapToScene(QPointF(item->width() / 2, item->height() / 2)).toPoint();
}

static QQuickItem *visibleItemWithText(QQuickWindow *window, const QString &text) {
    const auto items = window->findChildren<QQuickItem *>();
    for (QQuickItem *item : items) {
        if (!item->isVisible())
            continue;
        if (item->property("text").toString() == text)
            return item;
    }
    return nullptr;
}

static bool visibleTextStartsWith(QQuickWindow *window, const QString &prefix) {
    const auto items = window->findChildren<QQuickItem *>();
    for (QQuickItem *item : items) {
        if (!item->isVisible())
            continue;
        if (item->property("text").toString().startsWith(prefix))
            return true;
    }
    return false;
}

static QString labelFitError(QQuickWindow *window, const QString &label) {
    QQuickItem *match = visibleItemWithText(window, label);
    if (!match)
        return label + QStringLiteral(" is missing");
    if (match->implicitWidth() <= 0)
        return label + QStringLiteral(" has no width");
    if (match->width() + 1.0 < match->implicitWidth()) {
        return QStringLiteral("%1 width %2 is under its text width %3")
            .arg(label)
            .arg(match->width())
            .arg(match->implicitWidth());
    }
    return {};
}

static QString mainQmlPath() {
    return QFileInfo(QString::fromUtf8(__FILE__)).dir().absoluteFilePath(
        QStringLiteral("../src/Main.qml"));
}

// Loads Main.qml against a stub backend and keeps the engine alive for as long
// as the window is in use, so each shortcut test is just the key presses.
class QmlHarness {
public:
    explicit QmlHarness(ShortcutBackend &backend) {
        m_engine.addImageProvider(QStringLiteral("thumbs"), new ThumbProvider);
        m_engine.rootContext()->setContextProperty(QStringLiteral("backend"), &backend);
        m_engine.load(QUrl::fromLocalFile(mainQmlPath()));
        if (!m_engine.rootObjects().isEmpty())
            m_window = qobject_cast<QQuickWindow *>(m_engine.rootObjects().first());
    }

    QQuickWindow *window() const { return m_window; }
    QQmlApplicationEngine &engine() { return m_engine; }
    QQuickItem *editBar() const {
        return m_window ? m_window->findChild<QQuickItem *>(QStringLiteral("editBar")) : nullptr;
    }

private:
    QQmlApplicationEngine m_engine;
    QQuickWindow *m_window = nullptr;
};

class BackendTests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void openDialogDelegatesToFilePicker();
    void trayOrdersFiles();
    void droppedDirectoryAddsVideosOldestFirst();
    void cutListRoundTripsOrderAndMode();
    void dropSelectUnkeepsALine();
    void missingFileBlocksCut();
    void busyIgnoresTrayEdits();
    void shotRowThumbArrives();
    void shotThumbReusedUntilTheClipChanges();
    void speechWithoutKeyDoesNotStart();
    void savedKeyLoadsAndEnvironmentKeyIsNotStored();
    void typedKeyStaysInTheChildEnvironment();
    void gatherLabelsFit();
    void cutLaunchUsesTheCliOrUv();
    void sceneTransitionRoundTrips();
    void cutStatusLines();
    void pickerSelectionLoadsVideo();
    void thumbnailSlotsAreExposedImmediately();
    void thumbProviderUsesRevisionPrefixedIds();
    void thumbProviderScalesHeightOnlyRequests();
    void thumbnailWorkerStopsBlockedJobs();
    void exportDialogDelegatesSuggestedUrl();
    void suggestedExportUrlAlwaysUsesMp4();
    void exportClipWritesMp4();
    void exportKeepsOnlyTheClipsFromTheDialog();
    void exportClipCanReplaceSourceFile();
    void exportZeroLengthClipFails();
    void exportRefusesRewrittenPathOverExistingFile();
    void exportStartFailureClearsBusy();
    void failedExportPreservesExistingFile();
    void qmlDoesNotCreateAudioOutputWithoutVideo();
    void qmlShortcutsTriggerBackendActions();
    void qmlArrowKeysMoveThePlayhead();
    void qmlSpaceChordsSetTheClipEdges();
    void qmlKeysSplitRemoveAndRestoreClips();
    void qmlBracketsJumpBetweenClipEdges();
    void qmlZoomFocusesTheClip();
    void qmlQuitConfirmsUnexportedEdit();
    void qmlLooseCutAsksToSaveOrLose();
    void renderedCutCopiesInsteadOfEncoding();
    void savedCutCopiesTheCaptionFile();
    void timelineSplitsTrimsAndJoins();
    void timelineUndoesAGestureAsOneStep();
    void timelineTracksUnexportedCuts();
    void timelineAnswersWhereTimesFall();
    void timelineEditsAtATime();
    void timelineLoadsKeepRangesAsOneUndoStep();
    void keepListParsesAndResolvesSource();
    void keepListRejectsBadFiles();
    void keepListLoadsVideoWithClips();
    void trimArgsReencodeForPreciseCuts();
    void trimArgsConcatenateTheRanges();
    void trimArgsScaleTheShorterSide();
    void trimArgsUsesVaapiWhenGivenADevice();
    void exportHeightsNeverUpscale();
    void themeAccentReadsOmarchyColors();
    void themeAccentForegroundKeepsContrast();

private:
    QUrl videoUrl() const { return QUrl::fromLocalFile(m_videoPath); }
    QString formatName(const QString &path) const;
    // A test pattern, with a tone when audio is set, written into m_dir.
    QString makeVideo(const QString &name, double duration, bool audio);
    void waitForBackgroundWork(Backend &backend);
    bool installBrokenFfmpeg(const QString &dirPath);

    QTemporaryDir m_dir;
    QString m_videoPath;
};

void BackendTests::initTestCase() {
    QQuickStyle::setStyle(QStringLiteral("Material"));
    QCoreApplication::setOrganizationName(QStringLiteral("gigasolo"));
    QCoreApplication::setApplicationName(QStringLiteral("botcut"));

    QVERIFY2(m_dir.isValid(), "temporary directory is valid");
    QSettings::setPath(QSettings::NativeFormat, QSettings::UserScope, m_dir.path());
    m_videoPath = m_dir.filePath(QStringLiteral("clip.mp4"));

    QVERIFY2(!QStandardPaths::findExecutable(QStringLiteral("ffmpeg")).isEmpty(), "ffmpeg is available");
    QVERIFY(!makeVideo(QStringLiteral("clip.mp4"), 1.0, false).isEmpty());
    QVERIFY(QFileInfo::exists(m_videoPath));
}

void BackendTests::waitForBackgroundWork(Backend &backend) {
    QTRY_VERIFY_WITH_TIMEOUT(backend.status().isEmpty(), 10000);
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
}

QString BackendTests::formatName(const QString &path) const {
    const QString ffprobe = QStandardPaths::findExecutable(QStringLiteral("ffprobe"));
    if (ffprobe.isEmpty())
        return {};

    QProcess proc;
    proc.start(ffprobe, {
        QStringLiteral("-v"),
        QStringLiteral("error"),
        QStringLiteral("-show_entries"),
        QStringLiteral("format=format_name"),
        QStringLiteral("-of"),
        QStringLiteral("default=noprint_wrappers=1:nokey=1"),
        path,
    });
    if (!proc.waitForFinished(10000))
        return {};
    if (proc.exitStatus() != QProcess::NormalExit || proc.exitCode() != 0)
        return {};
    return QString::fromUtf8(proc.readAllStandardOutput()).trimmed();
}

// Drop an "ffmpeg" into dirPath that always fails to start (its shebang points
// nowhere), for tests that prepend dirPath to PATH.
bool BackendTests::installBrokenFfmpeg(const QString &dirPath) {
    QFile fake(QDir(dirPath).filePath(QStringLiteral("ffmpeg")));
    if (!fake.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    fake.write("#!/definitely/missing/omacut-ffmpeg\n");
    fake.close();
    return fake.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner
                               | QFileDevice::ExeOwner);
}

void BackendTests::trayOrdersFiles() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString first = m_dir.filePath(QStringLiteral("one.mp4"));
    const QString second = m_dir.filePath(QStringLiteral("two.mp4"));
    QVERIFY(QFile(first).open(QIODevice::WriteOnly));
    QVERIFY(QFile(second).open(QIODevice::WriteOnly));
    const auto stamp = [](const QString &path, int day) {
        QFile file(path);
        if (!file.open(QIODevice::ReadWrite))
            return false;
        const QDateTime when(QDate(2020, 1, day), QTime(12, 0), QTimeZone::UTC);
        return file.setFileTime(when, QFileDevice::FileModificationTime);
    };
    QVERIFY(stamp(second, 1));
    QVERIFY(stamp(first, 2));
    backend.addTrayFiles({first, second, second});
    QCOMPARE(backend.tray(), (QStringList{QFileInfo(second).absoluteFilePath(),
                                          QFileInfo(first).absoluteFilePath()}));
    QCOMPARE(backend.trayIndex(), 0);
    backend.moveTray(-1);
    QCOMPARE(backend.tray().first(), QFileInfo(second).absoluteFilePath());
    backend.moveTray(1);
    QCOMPARE(backend.tray().first(), QFileInfo(first).absoluteFilePath());
    QCOMPARE(backend.trayIndex(), 1);
    backend.removeTray();
    QCOMPARE(backend.tray().size(), 1);
    QCOMPARE(backend.cutMode(), QStringLiteral("speech"));
    backend.setCutMode(QStringLiteral("assemble"));
    QCOMPARE(backend.cutMode(), QStringLiteral("assemble"));
    backend.setCutMode(QStringLiteral("nope"));
    QCOMPARE(backend.cutMode(), QStringLiteral("assemble"));
}

void BackendTests::droppedDirectoryAddsVideosOldestFirst() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVERIFY(backend.gathering());
    QCOMPARE(backend.previewUrl(), QUrl());

    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    const QString root = dir.path();
    QVERIFY(QDir(root).mkpath(QStringLiteral("nested")));
    const auto touch = [](const QString &path) {
        QFile file(path);
        return file.open(QIODevice::WriteOnly);
    };
    const QString older = QDir(root).filePath(QStringLiteral("b.mp4"));
    const QString newer = QDir(root).filePath(QStringLiteral("a.MOV"));
    QVERIFY(touch(older));
    QVERIFY(touch(newer));
    QVERIFY(touch(QDir(root).filePath(QStringLiteral("note.txt"))));
    QVERIFY(touch(QDir(root).filePath(QStringLiteral(".hidden.mp4"))));
    QVERIFY(touch(QDir(root).filePath(QStringLiteral("nested/c.mp4"))));
    const auto stamp = [](const QString &path, int day) {
        QFile file(path);
        if (!file.open(QIODevice::ReadWrite))
            return false;
        const QDateTime when(QDate(2020, 6, day), QTime(8, 0), QTimeZone::UTC);
        return file.setFileTime(when, QFileDevice::FileModificationTime);
    };
    QVERIFY(stamp(older, 1));
    QVERIFY(stamp(newer, 3));

    backend.addDropped({QUrl::fromLocalFile(root)});
    const QString first = QFileInfo(older).absoluteFilePath();
    const QString second = QFileInfo(newer).absoluteFilePath();
    QCOMPARE(backend.tray(), (QStringList{first, second}));
    QCOMPARE(backend.trayIndex(), 0);
    QCOMPARE(backend.previewUrl(), QUrl::fromLocalFile(first));
    QVERIFY(backend.gathering());

    backend.setTrayIndex(1);
    QCOMPARE(backend.previewUrl(), QUrl::fromLocalFile(second));

    // Birth time on a copy is newer than the camera's modified time. The older
    // camera time must win, even when the name and the birth time say otherwise.
    const QString copiedNewer = m_dir.filePath(QStringLiteral("a-new.mp4"));
    const QString copiedOlder = m_dir.filePath(QStringLiteral("z-old.mp4"));
    const QString skip = m_dir.filePath(QStringLiteral("notes.txt"));
    QVERIFY(touch(copiedNewer));
    QTest::qSleep(1100);
    QVERIFY(touch(copiedOlder));
    QVERIFY(touch(skip));
    const auto stampModified = [](const QString &path, const QDate &modified) {
        QFile file(path);
        if (!file.open(QIODevice::ReadWrite))
            return false;
        return file.setFileTime(QDateTime(modified, QTime(12, 0), QTimeZone::UTC),
                                 QFileDevice::FileModificationTime);
    };
    QVERIFY(stampModified(copiedNewer, QDate(2019, 6, 1)));
    QVERIFY(stampModified(copiedOlder, QDate(2019, 1, 1)));
    backend.addDropped({QUrl::fromLocalFile(skip), QUrl::fromLocalFile(copiedNewer),
                        QUrl::fromLocalFile(copiedOlder),
                        QUrl(QStringLiteral("https://example.com/nope.mp4"))});
    QCOMPARE(backend.tray(), (QStringList{first, second,
                                          QFileInfo(copiedOlder).absoluteFilePath(),
                                          QFileInfo(copiedNewer).absoluteFilePath()}));
    QCOMPARE(backend.previewUrl(), QUrl::fromLocalFile(second));

    backend.removeTray();
    backend.removeTray();
    backend.removeTray();
    backend.removeTray();
    QVERIFY(backend.tray().isEmpty());
    QCOMPARE(backend.previewUrl(), QUrl());
    QVERIFY(backend.gathering());
}

void BackendTests::cutListRoundTripsOrderAndMode() {
    const QString first = QStringLiteral("/tmp/clips/b.mp4");
    const QString second = QStringLiteral("/tmp/clips/a.MOV");
    const QByteArray bytes = writeCutList(QStringLiteral("assemble"), {second, first});
    const QString text = QString::fromUtf8(bytes);
    QVERIFY(text.contains(QStringLiteral("\"mode\": \"assemble\"")));
    QVERIFY(!text.contains(QStringLiteral("XAI")));
    QVERIFY(!text.contains(QStringLiteral("apiKey")));
    QVERIFY(!text.contains(QStringLiteral("supersecret")));

    QString mode;
    QStringList files;
    QString error;
    QString intent;
    QVERIFY(parseCutList(bytes, QStringLiteral("/unused"), &mode, &files, &error, &intent));
    QCOMPARE(mode, QStringLiteral("assemble"));
    QCOMPARE(files, (QStringList{second, first}));
    QCOMPARE(intent, defaultCutIntent());
    QVERIFY(text.contains(QStringLiteral("\"intent\"")));
    QVariantList noLines;
    QVERIFY(parseCutList(bytes, QStringLiteral("/unused"), &mode, &files, &error, &intent, &noLines));
    QVERIFY(noLines.isEmpty());

    QVariantMap kept;
    kept.insert(QStringLiteral("id"), 2);
    kept.insert(QStringLiteral("clip"), 0);
    kept.insert(QStringLiteral("start"), 1.25);
    kept.insert(QStringLiteral("end"), 3.5);
    kept.insert(QStringLiteral("text"), QStringLiteral("hello there"));
    kept.insert(QStringLiteral("keep"), true);
    kept.insert(QStringLiteral("reason"), QStringLiteral("story"));
    const QByteArray withLines = writeCutList(QStringLiteral("speech"), {second, first},
                                               QStringLiteral("A ride"), {kept});
    QVariantList parsedLines;
    QVERIFY(parseCutList(withLines, QStringLiteral("/unused"), &mode, &files, &error, &intent,
                         &parsedLines));
    QCOMPARE(mode, QStringLiteral("speech"));
    QCOMPARE(intent, QStringLiteral("A ride"));
    QCOMPARE(parsedLines.size(), 1);
    QCOMPARE(parsedLines.at(0).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello there"));
    QCOMPARE(parsedLines.at(0).toMap().value(QStringLiteral("keep")).toBool(), true);
    QCOMPARE(parsedLines.at(0).toMap().value(QStringLiteral("start")).toDouble(), 1.25);

    const QByteArray extra = QByteArrayLiteral(
        "{\"version\":1,\"mode\":\"speech\",\"apiKey\":\"supersecret\",\"files\":[\"a.mp4\"]}");
    QVERIFY(parseCutList(extra, QStringLiteral("/tmp/clips"), &mode, &files, &error, &intent));
    QCOMPARE(mode, QStringLiteral("speech"));
    QCOMPARE(files, (QStringList{QStringLiteral("/tmp/clips/a.mp4")}));
    QCOMPARE(intent, defaultCutIntent());
    const QByteArray rewritten = writeCutList(mode, files);
    QVERIFY(!QString::fromUtf8(rewritten).contains(QStringLiteral("supersecret")));
}

void BackendTests::dropSelectUnkeepsALine() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QVariantMap kept;
    kept.insert(QStringLiteral("id"), 2);
    kept.insert(QStringLiteral("clip"), 0);
    kept.insert(QStringLiteral("start"), 1.25);
    kept.insert(QStringLiteral("end"), 3.5);
    kept.insert(QStringLiteral("text"), QStringLiteral("hello there"));
    kept.insert(QStringLiteral("keep"), true);
    kept.insert(QStringLiteral("reason"), QStringLiteral("story"));
    const QString clip = m_dir.filePath(QStringLiteral("line.mp4"));
    QVERIFY(QFile(clip).open(QIODevice::WriteOnly));
    QFile list(m_dir.filePath(QStringLiteral("lines.botcut.json")));
    QVERIFY(list.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray bytes = writeCutList(QStringLiteral("speech"), {clip}, QStringLiteral("A ride"), {kept});
    QCOMPARE(list.write(bytes), bytes.size());
    list.close();

    backend.addDropped({QUrl::fromLocalFile(list.fileName())});
    QCOMPARE(backend.selects().size(), 1);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());

    backend.dropSelect(2);
    QVERIFY(!backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("reason")).toString(),
             QStringLiteral("dropped"));
    backend.dropSelect(2);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("reason")).toString(),
             QStringLiteral("dropped"));

    backend.restoreSelect(2);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("reason")).toString(),
             QStringLiteral("restored"));
}

void BackendTests::missingFileBlocksCut() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString real = m_dir.filePath(QStringLiteral("kept.mp4"));
    QVERIFY(QFile(real).open(QIODevice::WriteOnly));
    const QString missing = m_dir.filePath(QStringLiteral("gone.mp4"));
    QFile list(m_dir.filePath(QStringLiteral("cut.botcut.json")));
    QVERIFY(list.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray bytes = writeCutList(QStringLiteral("assemble"),
                                           {QFileInfo(real).absoluteFilePath(), missing});
    QCOMPARE(list.write(bytes), bytes.size());
    list.close();

    backend.addDropped({QUrl::fromLocalFile(list.fileName())});
    QCOMPARE(backend.tray(), (QStringList{QFileInfo(real).absoluteFilePath(),
                                          QFileInfo(missing).absoluteFilePath()}));
    QCOMPARE(backend.cutMode(), QStringLiteral("assemble"));
    QVERIFY(backend.trayMissing());
    QVERIFY(backend.gathering());
    backend.startCut();
    QCOMPARE(backend.status(), QStringLiteral("A file in the list is missing"));
    QVERIFY(!backend.busy());
    QVERIFY(!backend.status().contains(QStringLiteral("supersecret")));
}

void BackendTests::busyIgnoresTrayEdits() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    const QString a = m_dir.filePath(QStringLiteral("busy-a.mp4"));
    const QString b = m_dir.filePath(QStringLiteral("busy-b.mp4"));
    const QString c = m_dir.filePath(QStringLiteral("busy-c.mp4"));
    QVERIFY(QFile(a).open(QIODevice::WriteOnly));
    QVERIFY(QFile(b).open(QIODevice::WriteOnly));
    QVERIFY(QFile(c).open(QIODevice::WriteOnly));

    QVariantMap kept;
    kept.insert(QStringLiteral("id"), 1);
    kept.insert(QStringLiteral("text"), QStringLiteral("hello"));
    kept.insert(QStringLiteral("keep"), true);
    kept.insert(QStringLiteral("reason"), QStringLiteral("story"));
    QFile list(m_dir.filePath(QStringLiteral("busy-list.botcut.json")));
    QVERIFY(list.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray bytes = writeCutList(QStringLiteral("speech"),
                                           {QFileInfo(a).absoluteFilePath(),
                                            QFileInfo(b).absoluteFilePath()},
                                           QStringLiteral("A ride"), {kept});
    QCOMPARE(list.write(bytes), bytes.size());
    list.close();

    backend.addDropped({QUrl::fromLocalFile(list.fileName())});
    QCOMPARE(backend.tray().size(), 2);
    QCOMPARE(backend.cutMode(), QStringLiteral("speech"));
    QCOMPARE(backend.intent(), QStringLiteral("A ride"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));
    QCOMPARE(backend.selects().size(), 1);
    QVERIFY(backend.gathering());

    // Set the flag directly so this does not stop the thumbnail worker.
    backend.m_busy = true;
    const QStringList tray = backend.tray();
    const int index = backend.trayIndex();
    const int opens = picker->openCount;

    backend.addTrayFiles({c});
    backend.moveTray(1);
    backend.removeTray();
    QCOMPARE(backend.tray(), tray);
    QCOMPARE(backend.trayIndex(), index);

    QFile other(m_dir.filePath(QStringLiteral("busy-other.botcut.json")));
    QVERIFY(other.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray otherBytes = writeCutList(QStringLiteral("assemble"),
                                                {QFileInfo(c).absoluteFilePath()});
    QCOMPARE(other.write(otherBytes), otherBytes.size());
    other.close();
    backend.addDropped({QUrl::fromLocalFile(other.fileName())});
    backend.openCutListDialog();
    backend.openVideoDialog();
    backend.addVideosDialog();
    QCOMPARE(backend.tray(), tray);
    QCOMPARE(backend.cutMode(), QStringLiteral("speech"));
    QCOMPARE(picker->openCount, opens);

    backend.setCutMode(QStringLiteral("assemble"));
    backend.setIntent(QStringLiteral("shorter"));
    backend.setSceneTransition(QStringLiteral("off"));
    QCOMPARE(backend.cutMode(), QStringLiteral("speech"));
    QCOMPARE(backend.intent(), QStringLiteral("A ride"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));

    backend.dropSelect(1);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    backend.restoreSelect(1);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("reason")).toString(),
             QStringLiteral("story"));

    emit picker->openSelected(videoUrl());
    QVERIFY(backend.gathering());
    QVERIFY(backend.source().isEmpty());

    const QString saved = m_dir.filePath(QStringLiteral("saved-while-busy.botcut.json"));
    backend.writeCutListFile(QUrl::fromLocalFile(saved));
    QVERIFY(QFileInfo::exists(saved));
    QCOMPARE(backend.tray(), tray);
}

void BackendTests::shotRowThumbArrives() {
    const QString path = makeVideo(QStringLiteral("shot-thumb.mp4"), 3.0, false);
    QVERIFY(!path.isEmpty());

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.addTrayFiles({path});
    QTRY_VERIFY_WITH_TIMEOUT(!backend.trayThumb(path).isEmpty(), 15000);
    const QString thumb = backend.trayThumb(path);
    QVERIFY(QFileInfo(thumb).isFile());
    QVERIFY(QFileInfo(thumb).size() > 0);

    const int revision = backend.trayThumbRevision();
    backend.removeTray();
    backend.addTrayFiles({path});
    QCOMPARE(backend.trayThumb(path), thumb);
    QCOMPARE(backend.trayThumbRevision(), revision);
    QVERIFY(backend.m_trayThumbWorker == nullptr);
}

void BackendTests::shotThumbReusedUntilTheClipChanges() {
    const QString path = makeVideo(QStringLiteral("shot-thumb-cache.mp4"), 3.0, false);
    QVERIFY(!path.isEmpty());
    {
        ThumbProvider provider;
        Backend backend(&provider, new FakeFilePicker);
        backend.addTrayFiles({path});
        QTRY_VERIFY_WITH_TIMEOUT(!backend.trayThumb(path).isEmpty(), 15000);
        QVERIFY(!backend.trayThumbPending(path));
    }

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.addTrayFiles({path});
    const QString cached = backend.trayThumb(path);
    QVERIFY(!cached.isEmpty());
    QVERIFY(QFileInfo(cached).isFile());
    QVERIFY(backend.m_trayThumbWorker == nullptr);
    QVERIFY(!backend.trayThumbPending(path));

    QFile file(path);
    QVERIFY(file.open(QIODevice::ReadWrite));
    const QDateTime later = QFileInfo(path).lastModified().addSecs(120);
    QVERIFY(file.setFileTime(later, QFileDevice::FileModificationTime));
    file.close();
    backend.removeTray();
    backend.addTrayFiles({path});
    QVERIFY(backend.trayThumb(path).isEmpty());
    QVERIFY(backend.trayThumbPending(path));
    QVERIFY(backend.m_trayThumbWorker != nullptr);
}

void BackendTests::speechWithoutKeyDoesNotStart() {
    EnvVarGuard guard("XAI_API_KEY");
    qunsetenv("XAI_API_KEY");

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString real = m_dir.filePath(QStringLiteral("spoken.mp4"));
    QVERIFY(QFile(real).open(QIODevice::WriteOnly));
    backend.addTrayFiles({real});
    backend.setCutMode(QStringLiteral("speech"));
    backend.setApiKey(QStringLiteral("supersecret"));
    QVERIFY(backend.apiKeySet());
    backend.setApiKey(QString());
    QVERIFY(!backend.apiKeySet());

    backend.startCut();
    QCOMPARE(backend.status(), QStringLiteral("Set an xAI key for spoken cuts."));
    QVERIFY(!backend.busy());
    QVERIFY(!backend.status().contains(QStringLiteral("supersecret")));
}

void BackendTests::savedKeyLoadsAndEnvironmentKeyIsNotStored() {
    EnvVarGuard guard("XAI_API_KEY");
    qputenv("XAI_API_KEY", "from-env");

    MemoryKeyStore store;
    ThumbProvider provider;
    Backend withEnv(&provider, new FakeFilePicker, &store);
    QVERIFY(withEnv.apiKeySet());
    QCOMPARE(store.load(), QString());
    QVERIFY(!withEnv.status().contains(QStringLiteral("from-env")));

    qunsetenv("XAI_API_KEY");
    QVERIFY(!withEnv.apiKeySet());

    withEnv.setApiKey(QStringLiteral("supersecret"));
    QCOMPARE(store.load(), QStringLiteral("supersecret"));
    QVERIFY(withEnv.apiKeySet());
    QVERIFY(!withEnv.status().contains(QStringLiteral("supersecret")));

    ThumbProvider nextProvider;
    Backend next(&nextProvider, new FakeFilePicker, &store);
    QVERIFY(next.apiKeySet());
    next.setApiKey(QString());
    QCOMPARE(store.load(), QString());
    QVERIFY(!next.apiKeySet());
    QVERIFY(!next.status().contains(QStringLiteral("supersecret")));
}

void BackendTests::gatherLabelsFit() {
    ShortcutBackend backend(QUrl(), 0.0);
    backend.setTray({QStringLiteral("/tmp/one.mp4"), QStringLiteral("/tmp/two.mp4"),
                     QStringLiteral("/tmp/three.mp4"), QStringLiteral("/tmp/four.mp4")});
    QVariantList lines;
    for (int i = 0; i < 8; ++i) {
        QVariantMap line;
        line.insert(QStringLiteral("id"), i);
        line.insert(QStringLiteral("text"),
                    QStringLiteral("a spoken line that is long enough to fill the row"));
        line.insert(QStringLiteral("keep"), i % 2 == 0);
        line.insert(QStringLiteral("reason"), QStringLiteral("unique?"));
        lines.append(line);
    }
    backend.setSelects(lines);

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->resize(960, 640);
    window->show();
    QTest::qWait(100);

    QQuickItem *cut = window->findChild<QQuickItem *>(QStringLiteral("cutButton"));
    QVERIFY(cut);
    QVERIFY(cut->isVisible());
    const qreal cutTop = cut->mapToScene(QPointF(0, 0)).y();
    const qreal cutBottom = cut->mapToScene(QPointF(0, cut->height())).y();
    QVERIFY2(cutTop >= 0, qPrintable(QStringLiteral("cut top %1").arg(cutTop)));
    QVERIFY2(cutBottom <= window->height() + 1.0,
             qPrintable(QStringLiteral("cut bottom %1 is past the window bottom %2")
                            .arg(cutBottom)
                            .arg(window->height())));
    QVERIFY(visibleItemWithText(window, QStringLiteral("Lines")));
    QVERIFY2(labelFitError(window, QStringLiteral("Render")).isEmpty(),
             qPrintable(labelFitError(window, QStringLiteral("Render"))));

    const QStringList mainLabels{QStringLiteral("Open list"), QStringLiteral("Save list"),
                                 QStringLiteral("Trim one file")};
    for (const QString &label : mainLabels)
        QVERIFY2(labelFitError(window, label).isEmpty(), qPrintable(labelFitError(window, label)));
    QVERIFY(!visibleTextStartsWith(window, QStringLiteral("Keep each moment")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("This movie")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Spoken cuts")));

    QQuickItem *settings = window->findChild<QQuickItem *>(QStringLiteral("settingsButton"));
    QVERIFY(settings);
    QVERIFY(settings->isVisible());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(settings));
    QVERIFY(window->property("settingsOpen").toBool());

    const QStringList settingLabels{QStringLiteral("Spoken cuts"), QStringLiteral("This movie"),
                                    QStringLiteral("Dip to black between files")};
    for (const QString &label : settingLabels)
        QVERIFY2(labelFitError(window, label).isEmpty(), qPrintable(labelFitError(window, label)));
    QVERIFY(visibleTextStartsWith(window, QStringLiteral("Keep each moment")));

    QQuickItem *spoken = window->findChild<QQuickItem *>(QStringLiteral("spokenCutsBox"));
    QVERIFY(spoken);
    QVERIFY(spoken->isVisible());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(spoken));
    QCOMPARE(backend.cutMode(), QStringLiteral("assemble"));
    QVERIFY(!visibleTextStartsWith(window, QStringLiteral("Keep each moment")));
    QVERIFY2(labelFitError(window, QStringLiteral("Keeps every file, in this order.")).isEmpty(),
             qPrintable(labelFitError(window, QStringLiteral("Keeps every file, in this order."))));

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(spoken));
    QCOMPARE(backend.cutMode(), QStringLiteral("speech"));
    QVERIFY(visibleTextStartsWith(window, QStringLiteral("Keep each moment")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Keeps every file, in this order.")));
}

void BackendTests::typedKeyStaysInTheChildEnvironment() {
    QProcessEnvironment base;
    base.insert(QStringLiteral("PATH"), QStringLiteral("/usr/bin"));
    const QProcessEnvironment withKey = cutProcessEnvironment(base, QStringLiteral("supersecret"));
    QCOMPARE(withKey.value(QStringLiteral("XAI_API_KEY")), QStringLiteral("supersecret"));
    QCOMPARE(withKey.value(QStringLiteral("PATH")), QStringLiteral("/usr/bin"));

    const QProcessEnvironment untouched = cutProcessEnvironment(base, QString());
    QCOMPARE(untouched.value(QStringLiteral("XAI_API_KEY")), QString());

    const CutLaunch launch = cutRunLaunch({QStringLiteral("/tmp/a.mp4")}, QStringLiteral("speech"),
                                           QStringLiteral("/tmp/out"), QStringLiteral("/usr/bin/botcut-cli"),
                                           QString(), QString());
    QVERIFY(!launch.arguments.join(QStringLiteral(" ")).contains(QStringLiteral("supersecret")));
    QVERIFY(!launch.arguments.contains(QStringLiteral("XAI_API_KEY")));
}

void BackendTests::cutLaunchUsesTheCliOrUv() {
    const QStringList files{QStringLiteral("/tmp/a.mp4"), QStringLiteral("/tmp/b.mp4")};
    const CutLaunch direct = cutRunLaunch(files, QStringLiteral("assemble"), QStringLiteral("/tmp/out"),
                                           QStringLiteral("/usr/bin/botcut-cli"), QString(), QString());
    QCOMPARE(direct.program, QStringLiteral("/usr/bin/botcut-cli"));
    QCOMPARE(direct.arguments, (QStringList{QStringLiteral("run"), QStringLiteral("/tmp/a.mp4"),
                                             QStringLiteral("/tmp/b.mp4"), QStringLiteral("--out"),
                                             QStringLiteral("/tmp/out"), QStringLiteral("--mode"),
                                             QStringLiteral("assemble"), QStringLiteral("--intent"),
                                             defaultCutIntent(), QStringLiteral("--scene-transition"),
                                             QStringLiteral("dip")}));
    QVERIFY(direct.error.isEmpty());

    const CutLaunch viaUv = cutRunLaunch(files, QStringLiteral("speech"), QStringLiteral("/tmp/out"),
                                          QString(), QStringLiteral("/usr/bin/uv"),
                                          QStringLiteral("/home/lonbaker/code/botcut/cli"));
    QCOMPARE(viaUv.program, QStringLiteral("/usr/bin/uv"));
    QCOMPARE(viaUv.arguments.mid(0, 4),
             (QStringList{QStringLiteral("run"), QStringLiteral("--project"),
                          QStringLiteral("/home/lonbaker/code/botcut/cli"),
                          QStringLiteral("botcut-cli")}));
    QCOMPARE(viaUv.arguments.at(viaUv.arguments.indexOf(QStringLiteral("--mode")) + 1),
             QStringLiteral("speech"));
    QVERIFY(!viaUv.arguments.contains(QStringLiteral("--decide")));

    const CutLaunch decided = cutRunLaunch(files, QStringLiteral("speech"), QStringLiteral("/tmp/out"),
                                            QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(),
                                            QStringLiteral("a ride"), true);
    QCOMPARE(decided.arguments.at(decided.arguments.indexOf(QStringLiteral("--intent")) + 1),
             QStringLiteral("a ride"));
    QCOMPARE(decided.arguments.last(), QStringLiteral("--decide"));

    const CutLaunch missing = cutRunLaunch(files, QStringLiteral("assemble"), QStringLiteral("/tmp/out"),
                                            QString(), QString(), QString());
    QVERIFY(missing.program.isEmpty());
    QVERIFY(missing.error.contains(QStringLiteral("botcut-cli")));

    const CutLaunch review = cutReviewLaunch(QStringLiteral("/tmp/out/cuts.json"),
                                              QStringLiteral("/usr/bin/botcut-cli"), QString(), QString());
    QCOMPARE(review.arguments, (QStringList{QStringLiteral("review"), QStringLiteral("/tmp/out/cuts.json"),
                                             QStringLiteral("--no-open")}));

    const CutLaunch hard = cutRunLaunch(files, QStringLiteral("assemble"), QStringLiteral("/tmp/out"),
                                         QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(),
                                         QString(), false, QStringLiteral("off"));
    QCOMPARE(hard.arguments.at(hard.arguments.indexOf(QStringLiteral("--scene-transition")) + 1),
             QStringLiteral("off"));
    QVERIFY(!hard.arguments.contains(QStringLiteral("--decide")));

    const CutLaunch rendered = cutRenderLaunch(QStringLiteral("/tmp/out"),
                                                QStringLiteral("/usr/bin/botcut-cli"), QString(),
                                                QString(), QStringLiteral("weird"));
    QCOMPARE(rendered.arguments, (QStringList{QStringLiteral("render"), QStringLiteral("/tmp/out"),
                                               QStringLiteral("--scene-transition"),
                                               QStringLiteral("dip")}));

    const QString cutsPath = QStringLiteral("/tmp/out/cuts.json");
    const CutLaunch captions = cutCaptionsLaunch(cutsPath, QStringLiteral("/usr/bin/botcut-cli"),
                                                  QString(), QString());
    QCOMPARE(captions.program, QStringLiteral("/usr/bin/botcut-cli"));
    QCOMPARE(captions.arguments, (QStringList{QStringLiteral("captions"), cutsPath}));
    QVERIFY(!captions.arguments.contains(QStringLiteral("--burn")));
    QVERIFY(captions.error.isEmpty());

    const CutLaunch captionsUv = cutCaptionsLaunch(cutsPath, QString(), QStringLiteral("/usr/bin/uv"),
                                                    QStringLiteral("/home/lonbaker/code/botcut/cli"));
    QCOMPARE(captionsUv.program, QStringLiteral("/usr/bin/uv"));
    QCOMPARE(captionsUv.arguments.mid(0, 4),
             (QStringList{QStringLiteral("run"), QStringLiteral("--project"),
                          QStringLiteral("/home/lonbaker/code/botcut/cli"),
                          QStringLiteral("botcut-cli")}));
    QCOMPARE(captionsUv.arguments.mid(4), (QStringList{QStringLiteral("captions"), cutsPath}));
    QVERIFY(!captionsUv.arguments.contains(QStringLiteral("--burn")));

    const CutLaunch missingCaptions = cutCaptionsLaunch(QString(), QStringLiteral("/usr/bin/botcut-cli"),
                                                         QString(), QString());
    QVERIFY(missingCaptions.program.isEmpty());
    QCOMPARE(missingCaptions.error, QStringLiteral("No cuts.json"));

    const CutLaunch highlight = cutShortLaunch(cutsPath, QStringLiteral("/usr/bin/botcut-cli"),
                                                QString(), QString());
    QCOMPARE(highlight.program, QStringLiteral("/usr/bin/botcut-cli"));
    QCOMPARE(highlight.arguments, (QStringList{QStringLiteral("short"), cutsPath}));
    QVERIFY(highlight.error.isEmpty());

    const CutLaunch missingShort = cutShortLaunch(QString(), QString(), QString(), QString());
    QVERIFY(missingShort.program.isEmpty());
    QCOMPARE(missingShort.error, QStringLiteral("No cuts.json"));
}

void BackendTests::sceneTransitionRoundTrips() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend first(&provider, picker);
    QCOMPARE(first.sceneTransition(), QStringLiteral("dip"));
    first.setSceneTransition(QStringLiteral("off"));
    QCOMPARE(first.sceneTransition(), QStringLiteral("off"));

    auto *againPicker = new FakeFilePicker;
    Backend again(&provider, againPicker);
    QCOMPARE(again.sceneTransition(), QStringLiteral("off"));
    again.setSceneTransition(QStringLiteral("nope"));
    QCOMPARE(again.sceneTransition(), QStringLiteral("dip"));

    auto *thirdPicker = new FakeFilePicker;
    Backend third(&provider, thirdPicker);
    QCOMPARE(third.sceneTransition(), QStringLiteral("dip"));
    third.setSceneTransition(QStringLiteral("dip"));
    QCOMPARE(third.sceneTransition(), QStringLiteral("dip"));
}

void BackendTests::cutStatusLines() {
    QCOMPARE(cutStatusFromLine(QStringLiteral("Reading files")), QStringLiteral("Reading files"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Reading pictures")), QStringLiteral("Reading pictures"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Trying again")), QStringLiteral("Trying again"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Transcribing 2/4 clip.MP4")),
             QStringLiteral("Transcribing 2/4 clip.MP4"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Choosing takes")), QStringLiteral("Choosing takes"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Rendering 42%")), QStringLiteral("Rendering 42%"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Opening 42%")), QStringLiteral("Opening 42%"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Rendering 0%")), QStringLiteral("Rendering 0%"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Opening 100%")), QStringLiteral("Opening 100%"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("3 kept, 1 dropped")),
             QStringLiteral("3 kept, 1 dropped"));

    const QString filter = QStringLiteral(
        "[0:v]scale=3840:2160:force_original_aspect_ratio=decrease,"
        "pad=3840:2160:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24[v0]");
    QVERIFY(cutStatusFromLine(filter).isEmpty());
    QVERIFY(cutStatusFromLine(QStringLiteral("Authorization: Bearer supersecret")).isEmpty());
    QVERIFY(cutStatusFromLine(QString(220, QLatin1Char('x'))).isEmpty());
}

void BackendTests::openDialogDelegatesToFilePicker() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);

    backend.openVideoDialog();
    backend.openVideoDialog();

    QCOMPARE(picker->openCount, 2);
}

void BackendTests::pickerSelectionLoadsVideo() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy infoSpy(&backend, &Backend::infoChanged);
    QSignalSpy gatheringSpy(&backend, &Backend::gatheringChanged);
    QVERIFY(backend.gathering());

    emit picker->openSelected(videoUrl());

    QCOMPARE(infoSpy.count(), 1);
    QCOMPARE(gatheringSpy.count(), 1);
    QVERIFY(!backend.gathering());
    QCOMPARE(backend.source(), videoUrl());
    QVERIFY(backend.duration() > 0);
    waitForBackgroundWork(backend);
}

void BackendTests::thumbnailSlotsAreExposedImmediately() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy thumbsSpy(&backend, &Backend::thumbsChanged);

    QVERIFY(backend.load(videoUrl()));

    QVERIFY(backend.thumbCount() > 0);
    QCOMPARE(backend.thumbReadyCount(), 0);
    waitForBackgroundWork(backend);
    QCOMPARE(backend.thumbReadyCount(), backend.thumbCount());
    QVERIFY(thumbsSpy.count() > 2);
}

void BackendTests::thumbProviderUsesRevisionPrefixedIds() {
    ThumbProvider provider;
    provider.setImages(QVector<QImage>(2));

    QImage image(2, 2, QImage::Format_RGB32);
    image.fill(Qt::red);
    provider.setImage(1, image);

    QSize size;
    QVERIFY(provider.requestImage(QStringLiteral("4/0"), &size, QSize()).isNull());
    QVERIFY(!provider.requestImage(QStringLiteral("4/1"), &size, QSize()).isNull());
    QCOMPARE(size, image.size());
}

void BackendTests::thumbProviderScalesHeightOnlyRequests() {
    ThumbProvider provider;
    provider.setImages(QVector<QImage>(1));

    QImage image(200, 100, QImage::Format_RGB32);
    image.fill(Qt::red);
    provider.setImage(0, image);

    QSize originalSize;
    const QImage scaled = provider.requestImage(QStringLiteral("1/0"), &originalSize, QSize(0, 50));

    QCOMPARE(originalSize, image.size());
    QCOMPARE(scaled.size(), QSize(100, 50));
}

void BackendTests::thumbnailWorkerStopsBlockedJobs() {
    const QString sleepBin = QStandardPaths::findExecutable(QStringLiteral("sleep"));
    QVERIFY2(!sleepBin.isEmpty(), "sleep is available");

    QTemporaryDir pathDir;
    QVERIFY(pathDir.isValid());
    const QString fakeFfmpeg = pathDir.filePath(QStringLiteral("ffmpeg"));
    QFile fake(fakeFfmpeg);
    QVERIFY(fake.open(QIODevice::WriteOnly | QIODevice::Truncate));
    fake.write(QStringLiteral("#!/bin/sh\nexec \"%1\" 30\n").arg(sleepBin).toUtf8());
    fake.close();
    QVERIFY(fake.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner
                                | QFileDevice::ExeOwner));

    EnvVarGuard pathGuard("PATH");
    qputenv("PATH", QFile::encodeName(pathDir.path()));

    ThumbWorker worker(QStringLiteral("unused.mp4"), 0.0, 60.0, 4);
    worker.start();
    QTest::qWait(100);

    QElapsedTimer elapsed;
    elapsed.start();
    worker.requestStop();
    const bool stopped = worker.wait(2000);
    const qint64 elapsedMs = elapsed.elapsed();
    if (!stopped) {
        worker.terminate();
        worker.wait(2000);
    }

    QVERIFY2(stopped, qPrintable(QStringLiteral("worker did not stop within 2000 ms")));
    QVERIFY2(elapsedMs < 1500,
             qPrintable(QStringLiteral("worker stop took %1 ms").arg(elapsedMs)));
}

void BackendTests::exportDialogDelegatesSuggestedUrl() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);

    QVERIFY(backend.load(videoUrl()));
    waitForBackgroundWork(backend);
    backend.exportDialog();

    QCOMPARE(picker->exportCount, 1);
    QCOMPARE(picker->lastSuggestedUrl,
             QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("clip_trimmed.mp4"))));
}

void BackendTests::suggestedExportUrlAlwaysUsesMp4() {
    const QString renamedSource = m_dir.filePath(QStringLiteral("renamed-source.webm"));
    QVERIFY(QFile::copy(m_videoPath, renamedSource));

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);

    QVERIFY(backend.load(QUrl::fromLocalFile(renamedSource)));
    waitForBackgroundWork(backend);

    QCOMPARE(backend.suggestedExportUrl(),
             QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("renamed-source_trimmed.mp4"))));
}

void BackendTests::exportClipWritesMp4() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);
    QStringList statuses;
    connect(&backend, &Backend::statusChanged, [&backend, &statuses] {
        statuses << backend.status();
    });

    QVERIFY(backend.load(videoUrl()));
    waitForBackgroundWork(backend);

    const QString selectedPath = m_dir.filePath(QStringLiteral("actual-export.webm"));
    const QString mp4Path = m_dir.filePath(QStringLiteral("actual-export.mp4"));
    backend.exportClips(QUrl::fromLocalFile(selectedPath), edit::whole(1.0));

    QVERIFY(backend.busy());
    QCOMPARE(backend.status(), QStringLiteral("Exporting 0%"));
    QTRY_VERIFY_WITH_TIMEOUT(doneSpy.count() + failedSpy.count() > 0, 20000);

    QCOMPARE(failedSpy.count(), 0);

    // ffmpeg's -progress stream drove the status to a completed percentage.
    QVERIFY2(statuses.contains(QStringLiteral("Exporting 100%")),
             qPrintable(statuses.join(QStringLiteral(" | "))));
    QCOMPARE(doneSpy.count(), 1);
    QCOMPARE(doneSpy.first().at(0).toString(), mp4Path);
    QVERIFY(!backend.busy());
    QVERIFY(QFileInfo::exists(mp4Path));
    QVERIFY(!QFileInfo::exists(selectedPath));
    QVERIFY(ffmpeg::probe(mp4Path).ok);
    QVERIFY2(formatName(mp4Path).contains(QStringLiteral("mp4")),
             qPrintable(formatName(mp4Path)));
}

QString BackendTests::makeVideo(const QString &name, double duration, bool audio) {
    const QString path = m_dir.filePath(name);
    QStringList args = {
        QStringLiteral("-hide_banner"), QStringLiteral("-loglevel"), QStringLiteral("error"),
        QStringLiteral("-f"), QStringLiteral("lavfi"),
        QStringLiteral("-i"), QStringLiteral("testsrc=size=32x32:rate=1:duration=%1").arg(duration),
    };
    if (audio)
        args << QStringLiteral("-f") << QStringLiteral("lavfi")
             << QStringLiteral("-i") << QStringLiteral("sine=duration=%1").arg(duration)
             << QStringLiteral("-c:a") << QStringLiteral("aac");
    args << QStringLiteral("-pix_fmt") << QStringLiteral("yuv420p") << QStringLiteral("-y") << path;

    QProcess proc;
    proc.start(QStandardPaths::findExecutable(QStringLiteral("ffmpeg")), args);
    if (!proc.waitForFinished(10000) || proc.exitStatus() != QProcess::NormalExit || proc.exitCode() != 0)
        return {};
    return path;
}

void BackendTests::exportKeepsOnlyTheClipsFromTheDialog() {
    const QString sourcePath = makeVideo(QStringLiteral("spliced-source.mp4"), 3.0, true);
    QVERIFY(!sourcePath.isEmpty());

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);

    QVERIFY(backend.load(QUrl::fromLocalFile(sourcePath)));
    waitForBackgroundWork(backend);

    // Cut the middle second out: 0..1 and 2..3 survive.
    Timeline *timeline = backend.timeline();
    timeline->split(1.0);
    timeline->split(2.0);
    timeline->removeClip(1);
    QCOMPARE(timeline->clips(), (edit::Clips{{0.0, 1.0}, {2.0, 3.0}}));
    QVERIFY(timeline->unexported());

    // Edits made while the dialog is open don't change what it exports.
    backend.exportDialog();
    const edit::Clips exported = timeline->clips();
    timeline->removeClip(0);

    const QString outPath = m_dir.filePath(QStringLiteral("spliced.mp4"));
    emit picker->exportSelected(QUrl::fromLocalFile(outPath), 0);
    QTRY_VERIFY_WITH_TIMEOUT(doneSpy.count() + failedSpy.count() > 0, 20000);
    QCOMPARE(failedSpy.count(), 0);

    const ffmpeg::VideoInfo info = ffmpeg::probe(outPath);
    QVERIFY(info.ok);
    QVERIFY(info.audio);
    QVERIFY2(qAbs(info.duration - 2.0) < 0.15, qPrintable(QString::number(info.duration)));

    // Only the exported clips count as exported.
    QVERIFY(timeline->unexported());
    timeline->undo();
    QCOMPARE(timeline->clips(), exported);
    QVERIFY(!timeline->unexported());
}

void BackendTests::exportClipCanReplaceSourceFile() {
    const QString sourcePath = m_dir.filePath(QStringLiteral("replace-source.mp4"));
    QVERIFY(QFile::copy(m_videoPath, sourcePath));

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);

    QVERIFY(backend.load(QUrl::fromLocalFile(sourcePath)));
    waitForBackgroundWork(backend);

    backend.exportClips(QUrl::fromLocalFile(sourcePath), edit::whole(1.0));

    QVERIFY(backend.busy());
    QTRY_VERIFY_WITH_TIMEOUT(doneSpy.count() + failedSpy.count() > 0, 20000);

    QCOMPARE(failedSpy.count(), 0);
    QCOMPARE(doneSpy.count(), 1);
    QCOMPARE(doneSpy.first().at(0).toString(), sourcePath);
    QVERIFY(QFileInfo::exists(sourcePath));
    QVERIFY(ffmpeg::probe(sourcePath).ok);
    QVERIFY2(formatName(sourcePath).contains(QStringLiteral("mp4")),
             qPrintable(formatName(sourcePath)));
    QVERIFY(!QFileInfo::exists(sourcePath + QStringLiteral(".botcut-part.mp4")));
}

void BackendTests::exportZeroLengthClipFails() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);

    QVERIFY(backend.load(videoUrl()));
    waitForBackgroundWork(backend);

    const QString outPath = m_dir.filePath(QStringLiteral("empty-range.mp4"));
    backend.exportClips(QUrl::fromLocalFile(outPath), {});

    QCOMPARE(failedSpy.count(), 1);
    QCOMPARE(doneSpy.count(), 0);
    QVERIFY(!backend.busy());
    QVERIFY(!QFileInfo::exists(outPath));
}

void BackendTests::exportRefusesRewrittenPathOverExistingFile() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);

    QVERIFY(backend.load(videoUrl()));
    waitForBackgroundWork(backend);

    // The dialog confirmed "rewrite-target.webm"; forcing the .mp4 suffix
    // would land on this existing file the user was never asked about.
    const QString selectedPath = m_dir.filePath(QStringLiteral("rewrite-target.webm"));
    const QString mp4Path = m_dir.filePath(QStringLiteral("rewrite-target.mp4"));
    const QByteArray original("original contents");
    {
        QFile existing(mp4Path);
        QVERIFY(existing.open(QIODevice::WriteOnly | QIODevice::Truncate));
        existing.write(original);
        existing.close();
    }

    backend.exportClips(QUrl::fromLocalFile(selectedPath), edit::whole(1.0));

    QCOMPARE(failedSpy.count(), 1);
    QCOMPARE(doneSpy.count(), 0);
    QVERIFY(!backend.busy());

    QFile check(mp4Path);
    QVERIFY(check.open(QIODevice::ReadOnly));
    QCOMPARE(check.readAll(), original);
}

void BackendTests::exportStartFailureClearsBusy() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);

    QVERIFY(backend.load(videoUrl()));
    waitForBackgroundWork(backend);

    QTemporaryDir pathDir;
    QVERIFY(pathDir.isValid());
    QVERIFY(installBrokenFfmpeg(pathDir.path()));

    EnvVarGuard pathGuard("PATH");
    qputenv("PATH", QFile::encodeName(pathDir.path()) + ':' + qgetenv("PATH"));

    backend.exportClips(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("failed.mp4"))),
                        edit::whole(1.0));

    QVERIFY(backend.busy());
    QTRY_COMPARE_WITH_TIMEOUT(failedSpy.count(), 1, 5000);
    QVERIFY(!backend.busy());
    QVERIFY(backend.status().isEmpty());
    QVERIFY(!failedSpy.first().at(0).toString().isEmpty());
}

void BackendTests::failedExportPreservesExistingFile() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);

    QVERIFY(backend.load(videoUrl()));
    waitForBackgroundWork(backend);

    // A pre-existing destination file that a failed export must not clobber.
    const QString outPath = m_dir.filePath(QStringLiteral("keep-me.mp4"));
    const QByteArray original("original contents");
    {
        QFile existing(outPath);
        QVERIFY(existing.open(QIODevice::WriteOnly | QIODevice::Truncate));
        existing.write(original);
        existing.close();
    }

    // Force ffmpeg to fail to start, the same way exportStartFailureClearsBusy does.
    QTemporaryDir pathDir;
    QVERIFY(pathDir.isValid());
    QVERIFY(installBrokenFfmpeg(pathDir.path()));

    EnvVarGuard pathGuard("PATH");
    qputenv("PATH", QFile::encodeName(pathDir.path()) + ':' + qgetenv("PATH"));

    backend.exportClips(QUrl::fromLocalFile(outPath), edit::whole(1.0));
    QTRY_COMPARE_WITH_TIMEOUT(failedSpy.count(), 1, 5000);

    // The original file survives untouched, and no temp part file is left behind.
    QFile check(outPath);
    QVERIFY(check.open(QIODevice::ReadOnly));
    QCOMPARE(check.readAll(), original);
    QVERIFY(!QFileInfo::exists(outPath + QStringLiteral(".botcut-part.mp4")));
}

void BackendTests::qmlDoesNotCreateAudioOutputWithoutVideo() {
    ShortcutBackend backend(QUrl(), 0.0);
    QmlHarness harness(backend);

    QVERIFY2(harness.window(), qPrintable(mainQmlPath()));
    QVERIFY(harness.window()->property("audioOutputReady").isValid());
    QCOMPARE(harness.window()->property("audioOutputReady").toBool(), false);
}

void BackendTests::qmlShortcutsTriggerBackendActions() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            1.0);
    QmlHarness harness(backend);

    QVERIFY2(harness.window(), qPrintable(mainQmlPath()));
    QQuickWindow *window = harness.window();
    QTRY_VERIFY_WITH_TIMEOUT(window->property("audioOutputReady").toBool(), 3000);

    window->show();
    window->requestActivate();
    QTest::qWait(100);

    QTest::keyClick(window, Qt::Key_S, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.exportCount, 1, 3000);

    QTest::keyClick(window, Qt::Key_O, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.openCount, 1, 3000);

    // ? toggles the hotkey overlay, and Escape closes it again.
    QTest::keyClick(window, Qt::Key_Question);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("helpVisible").toBool(), true, 3000);
    QTest::keyClick(window, Qt::Key_Escape);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("helpVisible").toBool(), false, 3000);
    QCOMPARE(backend.openCount, 1);

    window->setProperty("settingsOpen", true);
    QVERIFY(window->property("settingsOpen").toBool());
    QTest::keyClick(window, Qt::Key_Escape);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("settingsOpen").toBool(), false, 3000);
}

// Brings Main.qml up against the stub backend, loaded and focused, ready for keys.
static QQuickWindow *showEditor(QmlHarness &harness, ShortcutBackend &backend) {
    QQuickWindow *window = harness.window();
    if (!window || !QTest::qWaitFor([window] { return window->property("audioOutputReady").toBool(); }, 3000))
        return nullptr;
    backend.announceInfo();
    window->show();
    window->requestActivate();
    QTest::qWait(100);
    return window;
}

static double playhead(QmlHarness &harness) {
    return harness.editBar()->property("playheadSec").toDouble();
}

void BackendTests::qmlArrowKeysMoveThePlayhead() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));
    QVERIFY(harness.editBar());
    QCOMPARE(backend.timeline.clips(), edit::whole(20.0));

    QTest::keyClick(window, Qt::Key_Right);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 1.0, 3000);

    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 6.0, 3000);

    QTest::keyClick(window, Qt::Key_Right, Qt::AltModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 6.2, 3000);

    QTest::keyClick(window, Qt::Key_Left, Qt::AltModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 6.0, 3000);

    QTest::keyClick(window, Qt::Key_Left, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 1.0, 3000);

    // Seeking never leaves the video, so this stops at the start instead of -4.
    QTest::keyClick(window, Qt::Key_Left);
    QTest::keyClick(window, Qt::Key_Left, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 0.0, 3000);

    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Space, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{5.0, 20.0}}), 3000);
}

void BackendTests::qmlSpaceChordsSetTheClipEdges() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));

    // Park the playhead at 15 s and pull the end in to it.
    for (int i = 0; i < 3; ++i)
        QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 15.0, 3000);
    QTest::keyClick(window, Qt::Key_Space, Qt::AltModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{0.0, 15.0}}), 3000);

    // Same for the start, at 5 s.
    QTest::keyClick(window, Qt::Key_Left, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Left, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 5.0, 3000);
    QTest::keyClick(window, Qt::Key_Space, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{5.0, 15.0}}), 3000);

    // The edges never cross: pulling the end onto the start leaves the clip be.
    QTest::keyClick(window, Qt::Key_Space, Qt::AltModifier);
    QTest::qWait(50);
    QCOMPARE(backend.timeline.clips(), (edit::Clips{{5.0, 15.0}}));

    // In the cut tail, the clip before the playhead grows out to it.
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    for (int i = 0; i < 3; ++i)
        QTest::keyClick(window, Qt::Key_Right);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 18.0, 3000);
    QTest::keyClick(window, Qt::Key_Space, Qt::AltModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{5.0, 18.0}}), 3000);
}

void BackendTests::qmlKeysSplitRemoveAndRestoreClips() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));

    // S splits the clip under the playhead, at 5 s and then at 10 s.
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_S);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {5.0, 20.0}}), 3000);
    QCOMPARE(window->property("unexported").toBool(), false);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_S);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {5.0, 10.0}, {10.0, 20.0}}), 3000);

    // X removes the clip under the playhead...
    QTest::keyClick(window, Qt::Key_X);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {5.0, 10.0}}), 3000);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("unexported").toBool(), true, 3000);

    // ...and in a gap, restores it, growing the clip before it back out.
    QTest::keyClick(window, Qt::Key_X);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {5.0, 20.0}}), 3000);

    // Delete removes too; a gap between clips restores by joining them.
    QTest::keyClick(window, Qt::Key_Left, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Left, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 0.0, 3000);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_S);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_S);
    QTest::keyClick(window, Qt::Key_Left);
    QTest::keyClick(window, Qt::Key_Delete);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {10.0, 20.0}}), 3000);
    QTest::keyClick(window, Qt::Key_X);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 20.0}}), 3000);

    // Undo steps back through each edit; redo steps forward again.
    QTest::keyClick(window, Qt::Key_Z, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {10.0, 20.0}}), 3000);
    QTest::keyClick(window, Qt::Key_Z, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {5.0, 10.0}, {10.0, 20.0}}), 3000);
    QTest::keyClick(window, Qt::Key_Z, Qt::ControlModifier | Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(),
                              (edit::Clips{{0.0, 5.0}, {10.0, 20.0}}), 3000);
}

void BackendTests::qmlBracketsJumpBetweenClipEdges() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));

    backend.timeline.split(5.0);
    backend.timeline.split(12.0);
    QTest::keyClick(window, Qt::Key_Right);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 1.0, 3000);

    QTest::keyClick(window, Qt::Key_BracketRight);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 5.0, 3000);
    QTest::keyClick(window, Qt::Key_BracketRight);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 12.0, 3000);
    QTest::keyClick(window, Qt::Key_BracketRight);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 20.0, 3000);
    QTest::keyClick(window, Qt::Key_BracketLeft);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 12.0, 3000);
    QTest::keyClick(window, Qt::Key_BracketLeft);
    QTest::keyClick(window, Qt::Key_BracketLeft);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 0.0, 3000);
}

void BackendTests::qmlZoomFocusesTheClip() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));
    QQuickItem *editBar = harness.editBar();

    // Trim to 5..15 and zoom from inside it: the clip fills 80% of the track,
    // so the window stretches an extra eighth of the clip on each side.
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Space, Qt::ControlModifier);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Space, Qt::AltModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{5.0, 15.0}}), 3000);
    QTest::keyClick(window, Qt::Key_Left, Qt::ShiftModifier);

    QTest::keyClick(window, Qt::Key_Z);
    QTRY_COMPARE_WITH_TIMEOUT(editBar->property("zoomed").toBool(), true, 3000);
    QCOMPARE(editBar->property("viewStartSec").toDouble(), 3.75);
    QCOMPARE(editBar->property("viewEndSec").toDouble(), 16.25);

    // The filmstrip regenerates for the window, so the thumbs match the zoom.
    QCOMPARE(backend.thumbRequestCount, 1);
    QCOMPARE(backend.lastThumbStart, 3.75);
    QCOMPARE(backend.lastThumbEnd, 16.25);

    // Tighten the clip while zoomed: end to the playhead at 10 s.
    QTest::keyClick(window, Qt::Key_Space, Qt::AltModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{5.0, 10.0}}), 3000);
    QTest::keyClick(window, Qt::Key_Left);

    // The clip changed since the zoom, so Z zooms again instead of out.
    QTest::keyClick(window, Qt::Key_Z);
    QTRY_COMPARE_WITH_TIMEOUT(editBar->property("viewStartSec").toDouble(), 4.375, 3000);
    QCOMPARE(editBar->property("viewEndSec").toDouble(), 10.625);
    QCOMPARE(editBar->property("zoomed").toBool(), true);
    QCOMPARE(backend.thumbRequestCount, 2);

    // Untouched since the last zoom, so Z now zooms back out to the whole video.
    QTest::keyClick(window, Qt::Key_Z);
    QTRY_COMPARE_WITH_TIMEOUT(editBar->property("zoomed").toBool(), false, 3000);
    QCOMPARE(backend.thumbRequestCount, 3);
    QCOMPARE(backend.lastThumbStart, 0.0);
    QCOMPARE(backend.lastThumbEnd, 20.0);
}

void BackendTests::qmlQuitConfirmsUnexportedEdit() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));

    // Trim the video, making the work unexported: Q now asks instead of quitting.
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Space, Qt::ControlModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{5.0, 20.0}}), 3000);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("unexported").toBool(), true, 3000);

    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);

    // Escape backs out of the confirmation.
    QTest::keyClick(window, Qt::Key_Escape);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), false, 3000);

    // The dialog is keyboard-driven: arrows move between the buttons instead
    // of seeking, and Enter presses the focused one. Right from the default
    // Export focus wraps around to Cancel, which closes without exporting.
    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QTest::keyClick(window, Qt::Key_Right);
    QTest::keyClick(window, Qt::Key_Return);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), false, 3000);
    QCOMPARE(backend.exportCount, 0);
    QCOMPARE(playhead(harness), 5.0);

    // Enter on the default Export focus exports, as does Ctrl+S.
    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QTest::keyClick(window, Qt::Key_Return);
    QTRY_COMPARE_WITH_TIMEOUT(backend.exportCount, 1, 3000);
    QCOMPARE(window->property("quitConfirmVisible").toBool(), false);

    // The buttons work with the mouse too: Cancel dismisses, Export exports.
    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QQuickItem *cancelButton = dialogButton(window, QStringLiteral("Cancel"));
    QVERIFY(cancelButton);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(cancelButton));
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), false, 3000);
    QCOMPARE(backend.exportCount, 1);

    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QQuickItem *exportButton = dialogButton(window, QStringLiteral("Export"));
    QVERIFY(exportButton);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(exportButton));
    QTRY_COMPARE_WITH_TIMEOUT(backend.exportCount, 2, 3000);
    QCOMPARE(window->property("quitConfirmVisible").toBool(), false);

    // A completed export cleans the edit; changing it again re-dirties.
    backend.announceExportDone();
    QTRY_COMPARE_WITH_TIMEOUT(window->property("unexported").toBool(), false, 3000);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTest::keyClick(window, Qt::Key_Space, Qt::AltModifier);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{5.0, 10.0}}), 3000);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("unexported").toBool(), true, 3000);

    // Confirming the quit really ends the app: the window closes instead of
    // being re-intercepted by onClosing, and Qt.quit() is requested too.
    QSignalSpy quitSpy(&harness.engine(), &QQmlApplicationEngine::quit);
    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QTest::keyClick(window, Qt::Key_Left);
    QTest::keyClick(window, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(!window->isVisible(), 3000);
    QCOMPARE(quitSpy.count(), 1);
}

void BackendTests::qmlLooseCutAsksToSaveOrLose() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    backend.setRenderedUnsaved(true);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));
    QCOMPARE(window->property("looseCut").toBool(), true);
    QCOMPARE(window->property("unexported").toBool(), false);

    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QVERIFY(dialogButton(window, QStringLiteral("Save")));
    QVERIFY(dialogButton(window, QStringLiteral("Lose it")));

    QTest::keyClick(window, Qt::Key_Return);
    QTRY_COMPARE_WITH_TIMEOUT(backend.exportCount, 1, 3000);
    QCOMPARE(window->property("quitConfirmVisible").toBool(), false);

    QSignalSpy quitSpy(&harness.engine(), &QQmlApplicationEngine::quit);
    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QTest::keyClick(window, Qt::Key_Left);
    QTest::keyClick(window, Qt::Key_Return);
    QTRY_VERIFY_WITH_TIMEOUT(!window->isVisible(), 3000);
    QCOMPARE(quitSpy.count(), 1);
    QCOMPARE(backend.exportCount, 1);
}

void BackendTests::renderedCutCopiesInsteadOfEncoding() {
    const QString seed = makeVideo(QStringLiteral("seed-for-copy.mp4"), 1.0, false);
    QVERIFY(!seed.isEmpty());
    const QString dirPath = QDir::temp().filePath(QStringLiteral("botcut-cut-save-test"));
    QVERIFY(QDir().mkpath(dirPath));
    const QString rough = QDir(dirPath).filePath(QStringLiteral("rough_cut.mp4"));
    QFile::remove(rough);
    QVERIFY(QFile::copy(seed, rough));

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QVERIFY(backend.load(QUrl::fromLocalFile(rough)));
    QVERIFY(backend.renderedUnsaved());
    const QString suggested = backend.suggestedExportUrl().toLocalFile();
    QVERIFY(!suggested.startsWith(QDir::temp().absolutePath()));
    QCOMPARE(QFileInfo(suggested).fileName(), QStringLiteral("cut.mp4"));

    const QString saved = m_dir.filePath(QStringLiteral("saved-cut.mp4"));
    QFile::remove(saved);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);
    emit picker->exportSelected(QUrl::fromLocalFile(saved), 0);
    QTRY_COMPARE_WITH_TIMEOUT(doneSpy.count(), 1, 5000);
    QCOMPARE(failedSpy.count(), 0);
    QVERIFY(QFileInfo::exists(saved));
    QVERIFY(!backend.renderedUnsaved());
    QCOMPARE(backend.source(), QUrl::fromLocalFile(saved));
    QCOMPARE(QFileInfo(saved).size(), QFileInfo(rough).size());
    QVERIFY(QFileInfo::exists(rough));
    QDir(dirPath).removeRecursively();
}

void BackendTests::savedCutCopiesTheCaptionFile() {
    const QString seed = makeVideo(QStringLiteral("seed-for-captions.mp4"), 1.0, false);
    QVERIFY(!seed.isEmpty());
    const QString dirPath = QDir::temp().filePath(QStringLiteral("botcut-cut-caption-test"));
    QVERIFY(QDir().mkpath(dirPath));
    const QString rough = QDir(dirPath).filePath(QStringLiteral("rough_cut.mp4"));
    QFile::remove(rough);
    QVERIFY(QFile::copy(seed, rough));

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QVERIFY(backend.load(QUrl::fromLocalFile(rough)));
    QVERIFY(!backend.roughCut());

    QFile cuts(QDir(dirPath).filePath(QStringLiteral("cuts.json")));
    QVERIFY(cuts.open(QIODevice::WriteOnly | QIODevice::Truncate));
    cuts.write("{}\n");
    cuts.close();
    QVERIFY(backend.roughCut());

    const QString srtBody = QStringLiteral("1\n00:00:00,000 --> 00:00:01,000\nHello\n");
    QFile srt(QDir(dirPath).filePath(QStringLiteral("rough_cut.srt")));
    QVERIFY(srt.open(QIODevice::WriteOnly | QIODevice::Truncate));
    srt.write(srtBody.toUtf8());
    srt.close();

    const QString saved = m_dir.filePath(QStringLiteral("saved-cut.mp4"));
    const QString savedSrt = m_dir.filePath(QStringLiteral("saved-cut.srt"));
    QFile::remove(saved);
    QFile::remove(savedSrt);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    emit picker->exportSelected(QUrl::fromLocalFile(saved), 0);
    QTRY_COMPARE_WITH_TIMEOUT(doneSpy.count(), 1, 5000);
    QCOMPARE(backend.source(), QUrl::fromLocalFile(saved));
    QVERIFY(!backend.roughCut());
    QVERIFY(backend.status().isEmpty());
    QFile copied(savedSrt);
    QVERIFY(copied.open(QIODevice::ReadOnly));
    QCOMPARE(QString::fromUtf8(copied.readAll()), srtBody);

    QVERIFY(backend.load(QUrl::fromLocalFile(rough)));
    const QString blocked = m_dir.filePath(QStringLiteral("blocked-cut.mp4"));
    const QString blockedSrt = m_dir.filePath(QStringLiteral("blocked-cut.srt"));
    QFile::remove(blocked);
    QDir(blockedSrt).removeRecursively();
    QVERIFY(QDir().mkpath(blockedSrt));
    QSignalSpy blockedDone(&backend, &Backend::exportDone);
    emit picker->exportSelected(QUrl::fromLocalFile(blocked), 0);
    QTRY_COMPARE_WITH_TIMEOUT(blockedDone.count(), 1, 5000);
    QVERIFY(QFileInfo::exists(blocked));
    QCOMPARE(backend.source(), QUrl::fromLocalFile(blocked));
    QVERIFY(QFileInfo(blockedSrt).isDir());
    QCOMPARE(backend.status(), QStringLiteral("Could not copy the captions."));
    QDir(blockedSrt).removeRecursively();
    QDir(dirPath).removeRecursively();
}

void BackendTests::timelineSplitsTrimsAndJoins() {
    Timeline timeline;
    timeline.reset(10.0);
    QCOMPARE(timeline.clips(), edit::whole(10.0));

    timeline.split(4.0);
    QCOMPARE(timeline.clips(), (edit::Clips{{0.0, 4.0}, {4.0, 10.0}}));
    // Too close to an edge to leave a clip worth keeping: no split.
    timeline.split(4.05);
    QCOMPARE(timeline.clips().size(), 2);

    // A clip grows into a gap, never over its neighbour.
    timeline.setClip(1, 6.0, 10.0);
    QCOMPARE(timeline.clips(), (edit::Clips{{0.0, 4.0}, {6.0, 10.0}}));
    timeline.setClip(1, 2.0, 10.0);
    QCOMPARE(timeline.clips(), (edit::Clips{{0.0, 4.0}, {4.0, 10.0}}));
    timeline.setClip(1, 6.0, 10.0);
    QCOMPARE(timeline.keptDuration(), 8.0);
    QCOMPARE(edit::kept(timeline.clips()), (QList<edit::Range>{{0.0, 4.0}, {6.0, 10.0}}));

    // Joining restores what lay between; the last clip can't be removed.
    timeline.joinClips(0);
    QCOMPARE(timeline.clips(), edit::whole(10.0));
    timeline.removeClip(0);
    QCOMPARE(timeline.clips(), edit::whole(10.0));

    // Touching clips export as one range.
    timeline.split(5.0);
    QCOMPARE(edit::kept(timeline.clips()), (QList<edit::Range>{{0.0, 10.0}}));
}

void BackendTests::timelineUndoesAGestureAsOneStep() {
    Timeline timeline;
    timeline.reset(10.0);
    QVERIFY(!timeline.canUndo());

    timeline.beginGesture();
    timeline.setClip(0, 1.0, 10.0);
    timeline.setClip(0, 2.0, 10.0);
    timeline.setClip(0, 3.0, 10.0);
    timeline.endGesture();
    QCOMPARE(timeline.clips(), (edit::Clips{{3.0, 10.0}}));

    timeline.undo();
    QCOMPARE(timeline.clips(), edit::whole(10.0));
    QVERIFY(!timeline.canUndo());
    timeline.redo();
    QCOMPARE(timeline.clips(), (edit::Clips{{3.0, 10.0}}));

    // A new edit drops the redo history, and a reset drops it all.
    timeline.undo();
    timeline.split(5.0);
    QVERIFY(!timeline.canRedo());
    timeline.reset(10.0);
    QVERIFY(!timeline.canUndo());
}

void BackendTests::timelineTracksUnexportedCuts() {
    Timeline timeline;
    timeline.reset(10.0);
    // Splits alone cut nothing, so there's nothing to lose.
    timeline.split(5.0);
    QVERIFY(!timeline.unexported());

    timeline.removeClip(1);
    QVERIFY(timeline.unexported());
    timeline.markExported(timeline.clips());
    QVERIFY(!timeline.unexported());
    timeline.undo();
    timeline.redo();
    QVERIFY(!timeline.unexported());
}

void BackendTests::timelineAnswersWhereTimesFall() {
    Timeline timeline;
    timeline.reset(20.0);
    timeline.split(5.0);
    timeline.split(10.0);
    timeline.split(15.0);
    timeline.removeClip(2);
    // Clips 0..5, 5..10 and 15..20, with 10..15 cut.
    QCOMPARE(timeline.clipAt(5.0), 1);
    QCOMPARE(timeline.clipAt(12.0), -1);
    QCOMPARE(timeline.gapAt(12.0), 2);
    QCOMPARE(timeline.gapAt(20.0), 3);

    // Playback steps over the gap and ends after the last clip.
    QCOMPARE(timeline.playableFrom(3.0), 3.0);
    QCOMPARE(timeline.playableFrom(12.0), 15.0);
    QCOMPARE(timeline.playableFrom(19.99), -1.0);

    QCOMPARE(timeline.edgeFrom(1.0, 1), 5.0);
    QCOMPARE(timeline.edgeFrom(10.0, 1), 15.0);
    QCOMPARE(timeline.edgeFrom(20.0, 1), 20.0);
    QCOMPARE(timeline.edgeFrom(15.0, -1), 10.0);
    QCOMPARE(timeline.edgeFrom(0.0, -1), 0.0);
}

void BackendTests::timelineEditsAtATime() {
    Timeline timeline;
    timeline.reset(20.0);
    timeline.split(5.0);
    timeline.split(10.0);

    // Removing in a clip, then restoring the gap it leaves, round-trips.
    timeline.removeOrRestoreAt(7.0);
    QCOMPARE(timeline.clips(), (edit::Clips{{0.0, 5.0}, {10.0, 20.0}}));
    timeline.removeOrRestoreAt(7.0);
    QCOMPARE(timeline.clips(), (edit::Clips{{0.0, 20.0}}));

    // Trimming in a clip moves its edge; in the head or tail, the next or
    // previous clip grows back out.
    timeline.trimTo(4.0, true);
    timeline.trimTo(16.0, false);
    QCOMPARE(timeline.clips(), (edit::Clips{{4.0, 16.0}}));
    timeline.trimTo(2.0, true);
    timeline.trimTo(18.0, false);
    QCOMPARE(timeline.clips(), (edit::Clips{{2.0, 18.0}}));
    timeline.restoreGap(0);
    timeline.restoreGap(1);
    QCOMPARE(timeline.clips(), edit::whole(20.0));

    // Dragging an edge past the other stops a minimum clip short of it.
    timeline.moveEdge(0, false, -3.0);
    QCOMPARE(timeline.clips(), (edit::Clips{{0.0, edit::minimumClip}}));
    timeline.moveEdge(0, true, 30.0);
    QCOMPARE(timeline.clips(), (edit::Clips{{0.0, edit::minimumClip}}));
}

void BackendTests::timelineLoadsKeepRangesAsOneUndoStep() {
    Timeline timeline;
    timeline.load(10.0, {{1.0, 3.0}, {5.0, 8.0}});
    QCOMPARE(timeline.clips(), (edit::Clips{{1.0, 3.0}, {5.0, 8.0}}));
    QVERIFY(timeline.unexported());
    QVERIFY(timeline.canUndo());
    timeline.undo();
    QCOMPARE(timeline.clips(), edit::whole(10.0));
}

void BackendTests::keepListParsesAndResolvesSource() {
    QString source, error;
    edit::Clips clips;
    QVERIFY(Backend::parseKeepList(R"({"source":"a.mp4","keep":[{"start":1,"end":2},{"start":3,"end":4.5}]})",
                                   QStringLiteral("/tmp/x"), &source, &clips, &error));
    QCOMPARE(source, QStringLiteral("/tmp/x/a.mp4"));
    QCOMPARE(clips.size(), 2);
}

void BackendTests::keepListRejectsBadFiles() {
    for (const QByteArray &json : {QByteArray("{}"), QByteArray(R"({"source":"a.mp4","keep":[]})"),
                                  QByteArray(R"({"source":"a.mp4","keep":[{"start":2,"end":2}]})"),
                                  QByteArray("nope")}) {
        QString source, error;
        edit::Clips clips;
        QVERIFY(!Backend::parseKeepList(json, QStringLiteral("/tmp"), &source, &clips, &error));
        QVERIFY(!error.isEmpty());
    }
}

void BackendTests::keepListLoadsVideoWithClips() {
    QVERIFY(!makeVideo(QStringLiteral("keep.mp4"), 4.0, false).isEmpty());
    QFile json(m_dir.filePath(QStringLiteral("keep.keep.json")));
    QVERIFY(json.open(QIODevice::WriteOnly));
    json.write(R"({"source":"keep.mp4","keep":[{"start":0.5,"end":1.5},{"start":2.5,"end":3.5}]})");
    json.close();
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVERIFY(backend.loadKeepList(QUrl::fromLocalFile(json.fileName())));
    QCOMPARE(backend.timeline()->clips(), (edit::Clips{{0.5, 1.5}, {2.5, 3.5}}));
    waitForBackgroundWork(backend);
}

void BackendTests::trimArgsReencodeForPreciseCuts() {
    const QStringList args = ffmpeg::trimArgs(QStringLiteral("in.mp4"),
                                              QStringLiteral("out.mp4"),
                                              {{0.25, 0.75}}, true);

    QVERIFY(args.contains(QStringLiteral("libx264")));
    QVERIFY(args.contains(QStringLiteral("aac")));
    QVERIFY(args.contains(QStringLiteral("+faststart")));
    QVERIFY(!args.contains(QStringLiteral("copy")));

    // The range is a fast input seek bounded by its length.
    const int seekAt = args.indexOf(QStringLiteral("-ss"));
    QCOMPARE(args.mid(seekAt, 6), (QStringList{"-ss", "0.250", "-t", "0.500", "-i", "in.mp4"}));

    // Progress reporting goes to stdout so the UI can show a percentage.
    const int progressAt = args.indexOf(QStringLiteral("-progress"));
    QVERIFY(progressAt >= 0);
    QCOMPARE(args.value(progressAt + 1), QStringLiteral("pipe:1"));
}

void BackendTests::trimArgsConcatenateTheRanges() {
    const QStringList args = ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                              {{0.0, 1.0}, {2.0, 3.5}}, true);
    QCOMPARE(args.count(QStringLiteral("-i")), 2);
    QCOMPARE(args.value(args.indexOf(QStringLiteral("-filter_complex")) + 1),
             QStringLiteral("[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]"));
    QVERIFY(args.contains(QStringLiteral("[a]")));

    // Without audio, only the video is joined and mapped.
    const QStringList silent = ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                                {{0.0, 1.0}, {2.0, 3.5}}, false);
    QCOMPARE(silent.value(silent.indexOf(QStringLiteral("-filter_complex")) + 1),
             QStringLiteral("[0:v:0][1:v:0]concat=n=2:v=1:a=0[v]"));
    QVERIFY(!silent.contains(QStringLiteral("[a]")));
    QVERIFY(!silent.contains(QStringLiteral("aac")));
}

void BackendTests::trimArgsScaleTheShorterSide() {
    const auto graphOf = [](const QStringList &args) {
        return args.value(args.indexOf(QStringLiteral("-filter_complex")) + 1);
    };

    // No scale request, no scale filter.
    QVERIFY(!graphOf(ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                      {{0.0, 1.0}}, true))
                 .contains(QStringLiteral("scale")));

    // The filter caps whichever side is shorter, keeping the aspect ratio for
    // portrait and landscape alike.
    QCOMPARE(graphOf(ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                      {{0.0, 1.0}}, true, 1080)),
             QStringLiteral("[0:v:0][0:a:0]concat=n=1:v=1:a=1[joined][a];"
                            "[joined]scale='if(gt(iw,ih),-2,1080)':'if(gt(iw,ih),1080,-2)'[v]"));
}

void BackendTests::trimArgsUsesVaapiWhenGivenADevice() {
    const QString device = QStringLiteral("/dev/dri/renderD128");
    const QStringList args = ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                              {{0.0, 1.0}, {2.0, 3.5}}, true, 1080, device, 3840, 2160, 0);
    QCOMPARE(args.count(QStringLiteral("-hwaccel")), 2);
    QVERIFY(!args.contains(QStringLiteral("libx264")));
    QVERIFY(args.contains(QStringLiteral("h264_vaapi")));
    QCOMPARE(args.value(args.indexOf(QStringLiteral("-qp")) + 1), QStringLiteral("20"));
    const QString graph = args.value(args.indexOf(QStringLiteral("-filter_complex")) + 1);
    QVERIFY(graph.contains(QStringLiteral(
        "scale_vaapi=1920:1080:format=nv12:force_original_aspect_ratio=decrease")));
    QVERIFY(graph.contains(QStringLiteral(
        "hwdownload,format=nv12,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=nv12,hwupload")));
    QVERIFY(!graph.contains(QStringLiteral("pad_vaapi")));
    QVERIFY(graph.contains(QStringLiteral("concat=n=2:v=1:a=1[v][a]")));

    const QStringList full = ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                              {{0.25, 0.75}}, false, 0, device, 3840, 2160, 0);
    QVERIFY(!full.contains(QStringLiteral("aac")));
    const QString fullGraph = full.value(full.indexOf(QStringLiteral("-filter_complex")) + 1);
    QVERIFY(fullGraph.contains(QStringLiteral(
        "scale_vaapi=format=nv12,hwdownload,format=nv12,setsar=1,format=nv12,hwupload")));
    QVERIFY(!fullGraph.contains(QStringLiteral("pad=")));

    const QStringList turned = ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                                {{0.0, 1.0}}, true, 0, device, 1920, 1080, -90);
    QVERIFY(!turned.contains(QStringLiteral("-hwaccel")));
    QVERIFY(turned.contains(QStringLiteral("h264_vaapi")));
    QVERIFY(turned.value(turned.indexOf(QStringLiteral("-filter_complex")) + 1)
                .contains(QStringLiteral("hwupload")));

    // 1 fps stays on the CPU decoder. Hardware decode segfaults on this Arc.
    const QStringList slow = ffmpeg::trimArgs(QStringLiteral("in.mp4"), QStringLiteral("out.mp4"),
                                              {{0.0, 1.0}}, false, 0, device, 32, 32, 0, 1.0);
    QVERIFY(!slow.contains(QStringLiteral("-hwaccel")));
    QVERIFY(slow.contains(QStringLiteral("h264_vaapi")));
    QVERIFY(slow.value(slow.indexOf(QStringLiteral("-filter_complex")) + 1)
                .contains(QStringLiteral("hwupload")));
}

void BackendTests::exportHeightsNeverUpscale() {
    QCOMPARE(Backend::exportHeights(3840, 2160), (QList<int>{1080, 720}));
    // Portrait sources are judged by their shorter side too.
    QCOMPARE(Backend::exportHeights(2160, 3840), (QList<int>{1080, 720}));
    QCOMPARE(Backend::exportHeights(1920, 1080), (QList<int>{720}));
    // At or below a target there's nothing to gain, so it isn't offered.
    QCOMPARE(Backend::exportHeights(1280, 720), QList<int>{});
    QCOMPARE(Backend::exportHeights(0, 0), QList<int>{});
}

void BackendTests::themeAccentReadsOmarchyColors() {
    const QString fallback = QStringLiteral("#FFD60A");
    const QString colorsPath = m_dir.filePath(QStringLiteral("colors.toml"));

    // No file at all — the non-omarchy case — keeps the fallback.
    QCOMPARE(Backend::accentFromColorsFile(m_dir.filePath(QStringLiteral("missing.toml")), fallback),
             fallback);

    const auto writeColors = [&colorsPath](const char *contents) {
        QFile file(colorsPath);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        file.write(contents);
    };

    writeColors("# omarchy theme\n"
                "mode = \"dark\"\n"
                "background = \"#121212\"\n"
                "accent = \"#33ccff\"\n");
    QCOMPARE(Backend::accentFromColorsFile(colorsPath, fallback), QStringLiteral("#33ccff"));

    writeColors("accent = '#aabbcc'\n");
    QCOMPARE(Backend::accentFromColorsFile(colorsPath, fallback), QStringLiteral("#aabbcc"));

    // A value that isn't a color keeps the fallback rather than breaking bindings.
    writeColors("accent = \"not-a-color\"\n");
    QCOMPARE(Backend::accentFromColorsFile(colorsPath, fallback), fallback);

    // As does a theme without an accent at all.
    writeColors("background = \"#121212\"\n");
    QCOMPARE(Backend::accentFromColorsFile(colorsPath, fallback), fallback);
}

void BackendTests::themeAccentForegroundKeepsContrast() {
    QCOMPARE(Backend::foregroundFor(QStringLiteral("#FFD60A")), QStringLiteral("black"));
    QCOMPARE(Backend::foregroundFor(QStringLiteral("#222266")), QStringLiteral("white"));
    QCOMPARE(Backend::foregroundFor(QStringLiteral("garbage")), QStringLiteral("black"));
}

QTEST_MAIN(BackendTests)
#include "backend_tests.moc"
