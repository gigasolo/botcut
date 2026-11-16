#include <QtTest>
#include <functional>

#include <algorithm>
#include <csignal>

#include <QColor>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QElapsedTimer>
#include <QImage>
#include <QTimeZone>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJSEngine>
#include <QProcess>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlProperty>
#include <QQuickItem>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QRegularExpression>
#include <QSettings>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QVariantList>

#include "backend.h"
#include "theme.h"
#include "filepicker.h"
#include "portalfilepicker.h"
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

    void openVideos() override { ++openCount; }
    void openCutList() override {}
    void saveCutList(const QUrl &) override {}

    void exportVideo(const QUrl &suggestedUrl, const QList<int> &scaleHeights, int sourceWidth,
                     int sourceHeight) override {
        ++exportCount;
        lastSuggestedUrl = suggestedUrl;
        lastScaleHeights = scaleHeights;
        lastSourceWidth = sourceWidth;
        lastSourceHeight = sourceHeight;
    }

    int lastSourceWidth = -1;
    int lastSourceHeight = -1;
};

class RecordingPortal : public PortalFilePicker {
public:
    int requests = 0;
    QString method;
    QVariantMap options;

    QVariantMap quality() const { return qualityChoice(options); }

protected:
    void requestFile(const QString &method, const QString &title, QVariantMap options,
                     Action action) override {
        Q_UNUSED(title);
        Q_UNUSED(action);
        ++requests;
        this->method = method;
        this->options = options;
    }
};

class RecordedOpen : public QObject {
    Q_OBJECT

public:
    QList<QUrl> urls;

public slots:
    void open(const QUrl &url) { urls.append(url); }
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
    Q_PROPERTY(QString lastError READ lastError NOTIFY statusChanged)
    Q_PROPERTY(QString step READ step NOTIFY infoChanged)
    Q_PROPERTY(QString job READ job NOTIFY infoChanged)
    Q_PROPERTY(QString jobText READ jobText NOTIFY infoChanged)
    Q_PROPERTY(qreal progress READ progress NOTIFY infoChanged)
    Q_PROPERTY(QObject *timeline READ timelineObject CONSTANT)
    Q_PROPERTY(bool planCut READ planCut NOTIFY infoChanged)
    Q_PROPERTY(QObject *plan READ plan CONSTANT)

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
    bool busy() const { return m_busy; }
    void setBusy(bool busy) {
        if (m_busy == busy)
            return;
        m_busy = busy;
        emit busyChanged();
    }
    QString status() const { return {}; }
    QString lastError() const { return m_lastError; }
    void setLastError(const QString &error) {
        m_lastError = error;
        emit statusChanged();
    }
    Q_INVOKABLE void cancelJob() { ++cancelCount; }
    Q_INVOKABLE void dismissError() { setLastError(QString()); }
    int cancelCount = 0;
    QString step() const { return {}; }
    QString job() const { return m_job; }
    QString jobText() const { return m_job; }
    void setJob(const QString &job) {
        m_job = job;
        emit infoChanged();
    }
    qreal progress() const { return -1; }
    QObject *timelineObject() { return &timeline; }
    bool planCut() const { return m_planCut; }
    void setPlanCut(bool value) { m_planCut = value; }
    QObject *plan() { return &planFilm; }
    Q_INVOKABLE void exportPlan() {}

    Q_INVOKABLE bool load(const QUrl &) { return false; }
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
    Q_PROPERTY(QStringList brollFiles READ brollFiles NOTIFY infoChanged)
    Q_PROPERTY(bool brollMix READ brollMix WRITE setBrollMix NOTIFY infoChanged)
    Q_PROPERTY(QVariantList covers READ covers NOTIFY infoChanged)
    Q_PROPERTY(QStringList cutClips READ cutClips NOTIFY infoChanged)
    Q_PROPERTY(QString pace READ pace WRITE setPace NOTIFY infoChanged)
    Q_PROPERTY(double maxPause READ maxPause NOTIFY infoChanged)
    Q_PROPERTY(QVariantList chat READ chat NOTIFY chatChanged)
    Q_PROPERTY(bool proposalPending READ proposalPending NOTIFY chatChanged)
    Q_PROPERTY(bool canRevert READ canRevert NOTIFY infoChanged)
    Q_PROPERTY(QVariantList selects READ selects NOTIFY selectsChanged)
    Q_PROPERTY(QVariantList recentLists READ recentLists NOTIFY infoChanged)
    Q_PROPERTY(QVariantList recentCuts READ recentCuts NOTIFY infoChanged)
    void setTray(const QStringList &tray) { m_tray = tray; }
    void setSelects(const QVariantList &selects) {
        m_selects = selects;
        emit infoChanged();
        emit selectsChanged();
    }
    QStringList tray() const { return m_tray; }
    int trayIndex() const { return m_trayIndex; }
    void setTrayIndex(int index) {
        if (m_trayIndex == index)
            return;
        m_trayIndex = index;
        emit infoChanged();
    }
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
    QUrl previewUrl() const { return m_previewUrl; }
    void setPreviewUrl(const QUrl &url) {
        if (m_previewUrl == url)
            return;
        m_previewUrl = url;
        emit infoChanged();
    }
    void setSource(const QUrl &url) {
        if (m_source == url)
            return;
        m_source = url;
        emit infoChanged();
    }
    bool trayMissing() const { return false; }
    int trayThumbRevision() const { return 0; }
    bool apiKeySet() const { return false; }
    bool renderedUnsaved() const { return m_renderedUnsaved; }
    bool roughCut() const { return m_roughCut; }
    void setRoughCut(bool value) {
        if (m_roughCut == value)
            return;
        m_roughCut = value;
        emit infoChanged();
    }
    void setRenderedUnsaved(bool value) { m_renderedUnsaved = value; }
    QString intent() const { return m_intent; }
    void setIntent(const QString &value) {
        if (m_intent == value)
            return;
        m_intent = value;
        emit infoChanged();
    }
    QString sceneTransition() const { return m_sceneTransition; }
    void setSceneTransition(const QString &value) {
        const QString next = value == QLatin1String("off") ? QStringLiteral("off") : QStringLiteral("dip");
        if (next == m_sceneTransition)
            return;
        m_sceneTransition = next;
        emit infoChanged();
    }
    QStringList brollFiles() const { return m_brollFiles; }
    void setBrollFiles(const QStringList &files) {
        m_brollFiles = files;
        emit infoChanged();
    }
    Q_INVOKABLE bool isBroll(const QString &path) const { return m_brollFiles.contains(path); }
    Q_INVOKABLE void toggleBroll(int index) {
        lastToggleIndex = index;
        if (index < 0 || index >= m_tray.size())
            return;
        const QString path = m_tray.at(index);
        if (m_brollFiles.removeAll(path) == 0)
            m_brollFiles.append(path);
        emit infoChanged();
    }
    bool brollMix() const { return m_brollMix; }
    void setBrollMix(bool value) {
        if (m_brollMix == value)
            return;
        m_brollMix = value;
        emit infoChanged();
    }
    QVariantList covers() const { return m_covers; }
    void setCovers(const QVariantList &covers) { m_covers = covers; }
    QStringList cutClips() const { return m_cutClips; }
    void setCutClips(const QStringList &clips) { m_cutClips = clips; }
    Q_INVOKABLE void clearCover(int lineId) {
        for (int i = m_covers.size() - 1; i >= 0; --i) {
            if (m_covers.at(i).toMap().value(QStringLiteral("line")).toInt() == lineId)
                m_covers.removeAt(i);
        }
        emit infoChanged();
    }
    QString pace() const { return m_pace; }
    double maxPause() const { return 1; }
    QVariantList chat() const { return m_chat; }
    bool proposalPending() const { return m_proposalPending; }
    static QVariantMap turn(const QString &role, const QString &text, const QString &change = QString()) {
        QVariantMap row;
        row.insert(QStringLiteral("role"), role);
        row.insert(QStringLiteral("text"), text);
        row.insert(QStringLiteral("change"), change);
        return row;
    }
    void setChat(const QVariantList &turns, bool pending) {
        m_chat = turns;
        m_proposalPending = pending;
        emit chatChanged();
    }
    Q_INVOKABLE bool applyProposal() {
        ++applyCount;
        return m_acceptApply;
    }
    Q_INVOKABLE void dismissProposal() {
        ++dismissCount;
        m_proposalPending = false;
        emit chatChanged();
    }
    bool canRevert() const { return m_canRevert; }
    void setCanRevert(bool value) {
        if (m_canRevert == value)
            return;
        m_canRevert = value;
        emit infoChanged();
    }
    void setPace(const QString &pace) {
        if (pace == m_pace)
            return;
        m_pace = pace;
        emit infoChanged();
    }
    QVariantList selects() const { return m_selects; }
    QVariantList recentLists() const { return {}; }
    QVariantList recentCuts() const { return {}; }
    Q_INVOKABLE void dropSelect(int id) {
        lastDropId = id;
        for (int i = 0; i < m_selects.size(); ++i) {
            QVariantMap row = m_selects.at(i).toMap();
            if (row.value(QStringLiteral("id")).toInt() != id)
                continue;
            // A missing keep is kept, same as the row. An explicit false is already dropped.
            if (row.contains(QStringLiteral("keep")) && !row.value(QStringLiteral("keep")).toBool())
                return;
            row.insert(QStringLiteral("keep"), false);
            m_selects[i] = row;
            emit selectsChanged();
            return;
        }
    }
    Q_INVOKABLE void restoreSelect(int id) {
        lastRestoreId = id;
        for (int i = 0; i < m_selects.size(); ++i) {
            QVariantMap row = m_selects.at(i).toMap();
            if (row.value(QStringLiteral("id")).toInt() != id)
                continue;
            // A missing keep is already kept. The row reads keep, so a dropped line has to flip.
            if (!row.contains(QStringLiteral("keep")) || row.value(QStringLiteral("keep")).toBool())
                return;
            row.insert(QStringLiteral("keep"), true);
            m_selects[i] = row;
            emit selectsChanged();
            return;
        }
    }
    Q_INVOKABLE void renderSelects() { ++renderCount; }
    Q_INVOKABLE void writeCaptions() {}
    Q_INVOKABLE void makeShort() {}
    Q_INVOKABLE bool sendRevise(const QString &note) {
        lastRevise = note;
        return m_acceptRevise;
    }
    Q_INVOKABLE void revertRevise() {
        if (m_revertWorks)
            setCanRevert(false);
    }
    Q_INVOKABLE bool makeCard(const QString &, const QString &) { return false; }
    Q_INVOKABLE void addVideosDialog() {}
    Q_INVOKABLE void addDropped(const QList<QUrl> &) {}
    Q_INVOKABLE bool trayFileExists(const QString &) const { return true; }
    Q_INVOKABLE QString trayFileSize(const QString &) const { return QStringLiteral("1 MB"); }
    Q_INVOKABLE QString trayThumb(const QString &) const { return {}; }
    Q_INVOKABLE bool trayThumbPending(const QString &) const { return false; }
    Q_INVOKABLE void openCutListDialog() {}
    Q_INVOKABLE void saveCutListDialog() {}
    Q_INVOKABLE void reopenList(const QString &) {}
    Q_INVOKABLE void watchRecent(const QString &) {}
    Q_INVOKABLE void setApiKey(const QString &key) { savedKeys.append(key); }
    Q_INVOKABLE void checkApiKey() { ++keyCheckCount; }
    QStringList savedKeys;
    int keyCheckCount = 0;
    Q_INVOKABLE void moveTray(int delta) {
        lastMoveDelta = delta;
        ++moveCount;
    }
    Q_INVOKABLE void removeTray() {}
    Q_INVOKABLE void startCut() {}
    Q_INVOKABLE void exportDialog() {
        ++exportCount;
        exportedClips = timeline.clips();
    }
    Q_INVOKABLE void showFile() {
        shownDirectory = QFileInfo(m_source.toLocalFile()).absolutePath();
    }
    Q_INVOKABLE QUrl suggestedExportUrl() const { return {}; }
    Q_INVOKABLE void requestThumbs(double start, double end) {
        ++thumbRequestCount;
        lastThumbStart = start;
        lastThumbEnd = end;
    }
    Q_INVOKABLE void showShots() { ++showShotsCount; }
    Q_INVOKABLE void showMovie() {}
    Q_INVOKABLE void closeProject() {
        if (m_busy)
            return;
        ++closeCount;
        m_tray.clear();
        m_trayIndex = -1;
        m_selects.clear();
        m_source = QUrl();
        emit infoChanged();
        emit selectsChanged();
    }

    void announceInfo() {
        timeline.reset(m_duration);
        emit infoChanged();
    }
    void announceExportDone() {
        timeline.markExported(exportedClips);
        emit exportDone(QStringLiteral("/tmp/exported.mp4"));
    }

    Timeline timeline;
    PlanFilm planFilm;
    edit::Clips exportedClips;
    QString m_cutMode = QStringLiteral("speech");
    int openCount = 0;
    int exportCount = 0;
    int moveCount = 0;
    int lastMoveDelta = 0;
    QString shownDirectory;
    bool m_roughCut = false;
    int closeCount = 0;
    int showShotsCount = 0;
    bool m_acceptRevise = false;
    bool m_acceptApply = true;
    bool m_revertWorks = true;
    QString lastRevise;
    int applyCount = 0;
    int dismissCount = 0;
    int thumbRequestCount = 0;
    double lastThumbStart = 0;
    double lastThumbEnd = 0;
    int lastDropId = -1;
    int lastRestoreId = -1;
    int lastToggleIndex = -1;
    int renderCount = 0;

signals:
    void infoChanged();
    void thumbsChanged();
    void busyChanged();
    void statusChanged();
    void exportDone(const QString &path);
    void exportFailed(const QString &message);
    void loadError(const QString &message);
    void notice(const QString &message);
    void chatChanged();
    void selectsChanged();

private:
    QString m_lastError;
    QString m_job;
    QUrl m_source;
    QUrl m_previewUrl;
    double m_duration;
    QStringList m_tray;
    QVariantList m_selects;
    bool m_renderedUnsaved = false;
    QString m_sceneTransition = QStringLiteral("dip");
    QStringList m_brollFiles;
    bool m_brollMix = true;
    QVariantList m_covers;
    QStringList m_cutClips;
    QString m_pace = QStringLiteral("open");
    bool m_busy = false;
    bool m_canRevert = false;
    bool m_planCut = false;
    int m_trayIndex = -1;
    QString m_intent = defaultCutIntent();
    QVariantList m_chat;
    bool m_proposalPending = false;
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

static QQuickItem *visualItemWithText(QQuickItem *item, const QString &text, bool prefix) {
    if (!item || !item->isVisible())
        return nullptr;
    const QString value = item->property("text").toString();
    if (!value.isEmpty() && (prefix ? value.startsWith(text) : value == text))
        return item;
    const auto kids = item->childItems();
    for (QQuickItem *child : kids) {
        if (QQuickItem *found = visualItemWithText(child, text, prefix))
            return found;
    }
    return nullptr;
}

static void collectVisibleText(QQuickItem *item, const QString &text, QList<QQuickItem *> *out) {
    if (!item || !item->isVisible())
        return;
    if (item->property("text").toString() == text)
        out->append(item);
    const auto kids = item->childItems();
    for (QQuickItem *child : kids)
        collectVisibleText(child, text, out);
}

// Line rows are the only items that carry both selected and marked.
static QQuickItem *lineRowItem(QQuickItem *item) {
    for (QQuickItem *cursor = item; cursor; cursor = cursor->parentItem()) {
        if (cursor->property("selected").isValid() && cursor->property("marked").isValid())
            return cursor;
    }
    return nullptr;
}

static QQuickItem *visibleItemWithText(QQuickWindow *window, const QString &text) {
    const auto items = window->findChildren<QQuickItem *>();
    for (QQuickItem *item : items) {
        if (!item->isVisible())
            continue;
        if (item->property("text").toString() == text)
            return item;
    }
    // A RowLayout repeater reparents its labels in the visual tree without
    // leaving them in the window's QObject children.
    return window->contentItem() ? visualItemWithText(window->contentItem(), text, false) : nullptr;
}

static bool visibleTextStartsWith(QQuickWindow *window, const QString &prefix) {
    const auto items = window->findChildren<QQuickItem *>();
    for (QQuickItem *item : items) {
        if (!item->isVisible())
            continue;
        if (item->property("text").toString().startsWith(prefix))
            return true;
    }
    return window->contentItem() && visualItemWithText(window->contentItem(), prefix, true);
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
    explicit QmlHarness(ShortcutBackend &backend)
        : m_theme(QDir::temp().filePath(QStringLiteral("botcut-qml-theme")), nullptr, QString()) {
        m_engine.addImageProvider(QStringLiteral("thumbs"), new ThumbProvider);
        m_engine.rootContext()->setContextProperty(QStringLiteral("theme"), &m_theme);
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
    Theme m_theme;
    QQmlApplicationEngine m_engine;
    QQuickWindow *m_window = nullptr;
};

class BackendTests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void trayOrdersFiles();
    void droppedDirectoryAddsVideosOldestFirst();
    void cutListRoundTripsOrderAndMode();
    void dropSelectUnkeepsALine();
    void missingFileBlocksCut();
    void busyIgnoresTrayEdits();
    void recentListsAndCuts();
    void shotRowThumbArrives();
    void shotThumbReusedUntilTheClipChanges();
    void speechWithoutKeyDoesNotStart();
    void savedKeyLoadsAndEnvironmentKeyIsNotStored();
    void typedKeyStaysInTheChildEnvironment();
    void gatherLabelsFit();
    void planFadeSwitchWritesSceneTransition();
    void linesPaceIsTheShotsPace();
    void paceListKeysAndHide();
    void showFileOpensTheSavedFolder();
    void showFileOpensTheParentDirectory();
    void exportQualityNamesTheSourceSize();
    void lineRowDropStaysOnTheUnselectedRow();
    void reviseChatStates();
    void reviseFromMovieOpensLines();
    void listsAsksBeforeLeavingAHandTrim();
    void closeProjectKeepsTheFiles();
    void linePlayReachedEnd();
    void nextKeptAir();
    void cutRawWord();
    void pictureSentenceUnderThePicture();
    void planGapWashMarksADroppedLine();
    void cutLaunchUsesTheCliOrUv();
    void sceneTransitionRoundTrips();
    void clearCoverKeepsTheWords();
    void coverHoverNamesTheCutClip();
    void loadSelectsKeepsClipArrayOrder();
    void assembleLaunchOmitsBroll();
    void brollRoleRoundTrips();
    void coversKeepTheBeatWindow();
    void shotRowBrollWord();
    void coverAtWindow();
    void linesSentenceCountsCovers();
    void coverShowsInThePreview();
    void clearCoverTakesTheRun();
    void changeSentenceNamesTheBroll();
    void cutOpensTheChatWithTheEditorsReply();
    void renderSelectsPassesBrollSound();
    void planSegmentWriteLeavesCovers();
    void reviseDropsALineAndReverts();
    void cardLandsAtTheEndsOfTheTray();
    void helpNoteDoesNotReplayRevise();
    void failedLaunchKeepsTheReviseSnapshot();
    void missingProgramKeepsTheReviseSnapshot();
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
    void qmlKeysRemoveAndRestoreClips();
    void qmlPlainMovieLocksTrimWhileBusy();
    void qmlBracketsJumpBetweenClipEdges();
    void qmlZoomFocusesTheClip();
    void qmlQuitConfirmsUnexportedEdit();
    void qmlLooseCutAsksToSaveOrLose();
    void renderedCutCopiesInsteadOfEncoding();
    void renderedCutRefusesAnUpscale();
    void renderedCutDownscalesToTheChosenSize();
    void savedCutCopiesTheCaptionFile();
    void planWatchTrimsOneSourceAndRenders();
    void savedCutKeepsTheLineList();
    void timelineSplitsTrimsAndJoins();
    void timelineUndoesAGestureAsOneStep();
    void timelineTracksUnexportedCuts();
    void timelineAnswersWhereTimesFall();
    void timelineEditsAtATime();
    void timelineLoadsKeepRangesAsOneUndoStep();
    void trimArgsReencodeForPreciseCuts();
    void trimArgsConcatenateTheRanges();
    void trimArgsScaleTheShorterSide();
    void trimArgsUsesVaapiWhenGivenADevice();
    void exportHeightsNeverUpscale();
    void themeAccentReadsOmarchyColors();
    void themeAccentForegroundKeepsContrast();
    void themeReadsAccentForegroundAndRounding();
    void stepFollowsTheTrayAndTheLines();
    void jobFollowsTheStatusLine();
    void failedJobLeavesItsReasonOnScreen();
    void stopEndsTheJobAndItsChildrenQuietly();
    void restoreSelectSavesTheList();
    void captionsLandBesideTheSavedMovie();
    void qmlSentenceShowsTheLastError();
    void qmlStopButtonCancelsTheJob();
    void refusedKeyIsForgotten();
    void qmlSettingsSavesOnlyATypedKey();
    void qmlQuitAsksWhileAJobIsRunning();
    void grabWindowScreens();

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
    QVERIFY(!QString::fromUtf8(rewritten).contains(QStringLiteral("broll")));

    // B-roll marks ride along. An older list without them still opens.
    QStringList broll;
    QVERIFY(parseCutList(bytes, QStringLiteral("/unused"), &mode, &files, &error, &intent, nullptr, &broll));
    QVERIFY(broll.isEmpty());
    const QString card = QStringLiteral("/tmp/clips/botcut-card-1-open.mp4");
    const QByteArray marked = writeCutList(QStringLiteral("speech"), {second, first, card}, QString(), {},
                                           {first, card, QStringLiteral("/tmp/clips/nope.mp4")});
    QVERIFY(QString::fromUtf8(marked).contains(QStringLiteral("\"broll\"")));
    QVERIFY(!QString::fromUtf8(marked).contains(QStringLiteral("nope.mp4")));
    QVERIFY(parseCutList(marked, QStringLiteral("/unused"), &mode, &files, &error, &intent, nullptr, &broll));
    QCOMPARE(files, (QStringList{second, first, card}));
    // The card is dropped on the way in. A card is never B-roll.
    QCOMPARE(broll, QStringList{first});
    const QByteArray relative = QByteArrayLiteral(
        "{\"version\":1,\"mode\":\"speech\",\"files\":[\"a.mp4\",\"b.mp4\"],"
        "\"broll\":[\"b.mp4\",\"c.mp4\",7,\"b.mp4\"]}");
    QVERIFY(parseCutList(relative, QStringLiteral("/tmp/clips"), &mode, &files, &error, &intent, nullptr, &broll));
    QCOMPARE(files, (QStringList{QStringLiteral("/tmp/clips/a.mp4"), QStringLiteral("/tmp/clips/b.mp4")}));
    QCOMPARE(broll, QStringList{QStringLiteral("/tmp/clips/b.mp4")});
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

    const QString saved = m_dir.filePath(QStringLiteral("saved-while-busy.botcut.json"));
    backend.writeCutListFile(QUrl::fromLocalFile(saved));
    QVERIFY(QFileInfo::exists(saved));
    QCOMPARE(backend.tray(), tray);
}

void BackendTests::recentListsAndCuts() {
    QSettings().remove(QStringLiteral("recentLists"));
    QSettings().remove(QStringLiteral("recentCuts"));

    const QString a = m_dir.filePath(QStringLiteral("recent-a.mp4"));
    const QString b = m_dir.filePath(QStringLiteral("recent-b.mp4"));
    QVERIFY(QFile(a).open(QIODevice::WriteOnly));
    QVERIFY(QFile(b).open(QIODevice::WriteOnly));

    const QString movie = makeVideo(QStringLiteral("finished-cut.mp4"), 1.0, false);
    QVERIFY(!movie.isEmpty());
    const QString tempCut = m_dir.filePath(QStringLiteral("rough_cut.mp4"));
    const QString savedCut = m_dir.filePath(QStringLiteral("ride.mp4"));
    QVERIFY(QFile::copy(movie, tempCut));
    QVERIFY(QFile::copy(movie, savedCut));

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.addTrayFiles({a, b});
    const QString ride = m_dir.filePath(QStringLiteral("ride.botcut.json"));
    backend.writeCutListFile(QUrl::fromLocalFile(ride));
    QCOMPARE(backend.status(), QStringLiteral("Saved the list"));

    QVariantList lists = backend.recentLists();
    QCOMPARE(lists.size(), 1);
    QCOMPARE(lists.at(0).toMap().value(QStringLiteral("path")).toString(),
             QFileInfo(ride).absoluteFilePath());
    QCOMPARE(lists.at(0).toMap().value(QStringLiteral("name")).toString(), QStringLiteral("ride"));

    backend.writeCutListFile(QUrl::fromLocalFile(ride));
    QCOMPARE(backend.recentLists().size(), 1);

    backend.rememberFinishedCut(tempCut);
    QVariantList cuts = backend.recentCuts();
    QCOMPARE(cuts.size(), 1);
    QCOMPARE(cuts.at(0).toMap().value(QStringLiteral("path")).toString(),
             QFileInfo(tempCut).absoluteFilePath());
    const QString linked = cuts.at(0).toMap().value(QStringLiteral("list")).toString();
    QCOMPARE(linked, QFileInfo(ride).absoluteFilePath());
    QVERIFY(QFileInfo(linked).isFile());

    backend.rememberSavedCut(tempCut, savedCut);
    cuts = backend.recentCuts();
    QCOMPARE(cuts.size(), 1);
    QCOMPARE(cuts.at(0).toMap().value(QStringLiteral("path")).toString(),
             QFileInfo(savedCut).absoluteFilePath());
    QCOMPARE(cuts.at(0).toMap().value(QStringLiteral("list")).toString(), linked);

    backend.watchRecent(savedCut);
    QCOMPARE(backend.source(), QUrl::fromLocalFile(QFileInfo(savedCut).absoluteFilePath()));
    QVERIFY(!backend.gathering());
    waitForBackgroundWork(backend);

    const QString chosen = m_dir.filePath(QStringLiteral("chosen.botcut.json"));
    backend.writeCutListFile(QUrl::fromLocalFile(chosen));
    QCOMPARE(backend.recentLists().at(0).toMap().value(QStringLiteral("name")).toString(),
             QStringLiteral("chosen"));
    QCOMPARE(backend.recentCuts().at(0).toMap().value(QStringLiteral("list")).toString(),
             QFileInfo(chosen).absoluteFilePath());

    backend.reopenList(chosen);
    QVERIFY(backend.gathering());
    QCOMPARE(backend.tray().size(), 2);
    QCOMPARE(backend.source(), QUrl::fromLocalFile(QFileInfo(savedCut).absoluteFilePath()));

    const int listed = backend.recentLists().size();
    backend.reopenList(m_dir.filePath(QStringLiteral("missing.botcut.json")));
    QCOMPARE(backend.status(), QStringLiteral("That list can't be found"));
    QCOMPARE(backend.recentLists().size(), listed);
    QCOMPARE(backend.tray().size(), 2);

    backend.watchRecent(m_dir.filePath(QStringLiteral("never-stored.mp4")));
    QCOMPARE(backend.status(), QStringLiteral("That movie can't be found"));
    QCOMPARE(backend.recentCuts().size(), 1);
    QCOMPARE(backend.source(), QUrl::fromLocalFile(QFileInfo(savedCut).absoluteFilePath()));

    QVERIFY(QFile::remove(savedCut));
    backend.watchRecent(savedCut);
    QCOMPARE(backend.status(), QStringLiteral("That movie can't be found"));
    QCOMPARE(backend.recentCuts().size(), 0);

    backend.m_busy = true;
    const QStringList tray = backend.tray();
    const QUrl source = backend.source();
    backend.reopenList(chosen);
    backend.watchRecent(tempCut);
    QCOMPARE(backend.tray(), tray);
    QCOMPARE(backend.source(), source);
    QVERIFY(backend.gathering());
    QCOMPARE(backend.status(), QStringLiteral("That movie can't be found"));
    QCOMPARE(backend.recentCuts().size(), 0);
    backend.m_busy = false;

    for (int i = 0; i < 7; ++i)
        backend.writeCutListFile(QUrl::fromLocalFile(
            m_dir.filePath(QStringLiteral("cap-%1.botcut.json").arg(i))));
    lists = backend.recentLists();
    QCOMPARE(lists.size(), 6);
    QCOMPARE(lists.at(0).toMap().value(QStringLiteral("name")).toString(), QStringLiteral("cap-6"));
    QCOMPARE(lists.at(5).toMap().value(QStringLiteral("name")).toString(), QStringLiteral("cap-1"));

    const QString clip = m_dir.filePath(QStringLiteral("snapshot-src.mp4"));
    const QString snapMovie = m_dir.filePath(QStringLiteral("snapshot-movie.mp4"));
    QVERIFY(QFile::copy(movie, clip));
    QVERIFY(QFile::copy(movie, snapMovie));
    QString firstSnapshot;
    {
        ThumbProvider snapProvider;
        Backend snap(&snapProvider, new FakeFilePicker);
        snap.addTrayFiles({clip});
        snap.rememberFinishedCut(snapMovie);
        const QVariantMap row = snap.recentCuts().at(0).toMap();
        QCOMPARE(row.value(QStringLiteral("path")).toString(), QFileInfo(snapMovie).absoluteFilePath());
        firstSnapshot = row.value(QStringLiteral("list")).toString();
        QVERIFY(firstSnapshot.endsWith(QStringLiteral("/lists/snapshot-src.botcut.json")));
        QVERIFY(QFileInfo(firstSnapshot).isFile());
        QCOMPARE(snap.recentLists().at(0).toMap().value(QStringLiteral("path")).toString(), firstSnapshot);
    }
    QFile snapshotFile(firstSnapshot);
    QVERIFY(snapshotFile.open(QIODevice::ReadOnly));
    const QByteArray snapshotBytes = snapshotFile.readAll();
    snapshotFile.close();

    {
        ThumbProvider againProvider;
        Backend again(&againProvider, new FakeFilePicker);
        again.addTrayFiles({clip});
        again.rememberFinishedCut(snapMovie);
        const QString second = again.recentCuts().at(0).toMap().value(QStringLiteral("list")).toString();
        QVERIFY(second.contains(QStringLiteral("/lists/snapshot-src-")));
        QVERIFY(second.endsWith(QStringLiteral(".botcut.json")));
        QVERIFY(second != firstSnapshot);
        QVERIFY(QFileInfo(second).isFile());
        QCOMPARE(again.recentCuts().size(), 1);
    }
    QFile stillThere(firstSnapshot);
    QVERIFY(stillThere.open(QIODevice::ReadOnly));
    QCOMPARE(stillThere.readAll(), snapshotBytes);
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
    QStringList tray;
    for (int i = 0; i < 12; ++i)
        tray.append(QStringLiteral("/tmp/shot-%1.mp4").arg(i));
    backend.setTray(tray);
    QVariantList lines;
    for (int i = 0; i < 31; ++i) {
        QVariantMap line;
        line.insert(QStringLiteral("id"), i);
        line.insert(QStringLiteral("text"),
                    QStringLiteral("a spoken line that is long enough to fill the row"));
        line.insert(QStringLiteral("keep"), i < 24);
        line.insert(QStringLiteral("reason"), QStringLiteral("unique?"));
        if (i == 0) {
            line.insert(QStringLiteral("start"), 0.0);
            line.insert(QStringLiteral("end"), 5999.0);
        }
        lines.append(line);
    }
    backend.setSelects(lines);

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    QTest::qWait(50);
    window->resize(960, 640);
    QTest::qWait(100);

    const auto fullyInside = [&](QQuickItem *item, const QString &label) {
        if (!item || !item->isVisible())
            return label + QStringLiteral(" is missing");
        const QPointF topLeft = item->mapToScene(QPointF(0, 0));
        const QPointF bottomRight = item->mapToScene(QPointF(item->width(), item->height()));
        if (topLeft.x() < -1.0 || topLeft.y() < -1.0)
            return QStringLiteral("%1 origin %2,%3 is outside").arg(label).arg(topLeft.x()).arg(topLeft.y());
        if (bottomRight.x() > window->width() + 1.0 || bottomRight.y() > window->height() + 1.0) {
            return QStringLiteral("%1 ends at %2,%3 past %4x%5")
                .arg(label)
                .arg(bottomRight.x())
                .arg(bottomRight.y())
                .arg(window->width())
                .arg(window->height());
        }
        return QString();
    };
    const auto onScreen = [&](const QString &text) -> QQuickItem * {
        QQuickItem *fallback = nullptr;
        const auto take = [&](QQuickItem *item) {
            if (!item || !item->isVisible() || item->property("text").toString() != text)
                return false;
            if (!fallback)
                fallback = item;
            return fullyInside(item, text).isEmpty();
        };
        const auto items = window->findChildren<QQuickItem *>();
        for (QQuickItem *item : items) {
            if (take(item))
                return item;
        }
        // List delegates can sit in the visual tree without joining findChildren.
        QList<QQuickItem *> pending;
        if (window->contentItem())
            pending.append(window->contentItem());
        while (!pending.isEmpty()) {
            QQuickItem *item = pending.takeFirst();
            if (take(item))
                return item;
            const auto kids = item->childItems();
            for (QQuickItem *child : kids)
                pending.append(child);
        }
        return fallback;
    };
    QCOMPARE(window->property("currentLine").toInt(), 0);

    QQuickItem *cut = window->findChild<QQuickItem *>(QStringLiteral("cutButton"));
    QVERIFY(cut);
    QVERIFY(cut->isVisible());
    QVERIFY2(fullyInside(cut, QStringLiteral("Cut")).isEmpty(),
             qPrintable(fullyInside(cut, QStringLiteral("Cut"))));

    QQuickItem *settings = window->findChild<QQuickItem *>(QStringLiteral("settingsButton"));
    QVERIFY(settings);
    QVERIFY(settings->isVisible());

    QQuickItem *reviseField = window->findChild<QQuickItem *>(QStringLiteral("reviseField"));
    QVERIFY(reviseField);
    QVERIFY(reviseField->isVisible());
    QVERIFY2(fullyInside(reviseField, QStringLiteral("reviseField")).isEmpty(),
             qPrintable(fullyInside(reviseField, QStringLiteral("reviseField"))));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Send")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("Ask for a change\u2026")));
    QVERIFY(visibleItemWithText(window, defaultCutIntent()));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Search lines")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Previous")));
    const auto rowFit = [&](QQuickItem *item, const QString &label) {
        if (!item || !item->isVisible())
            return label + QStringLiteral(" is missing");
        QQuickItem *row = item->parentItem();
        const qreal end = item->mapToItem(row, QPointF(item->width(), 0)).x();
        if (end > row->width() + 1.0) {
            return QStringLiteral("%1 ends at %2 in a row %3 wide").arg(label).arg(end).arg(row->width());
        }
        const QString outside = fullyInside(item, label);
        if (!outside.isEmpty())
            return outside;
        const auto kids = item->childItems();
        for (QQuickItem *child : kids) {
            const QString text = child->property("text").toString();
            if (text.isEmpty() || !child->isVisible())
                continue;
            if (child->width() + 1.0 < child->implicitWidth()) {
                return QStringLiteral("%1 width %2 is under its text width %3")
                    .arg(text)
                    .arg(child->width())
                    .arg(child->implicitWidth());
            }
        }
        return QString();
    };
    for (const char *name : {"listsHome", "shotsStep", "linesStep", "movieStep"}) {
        QQuickItem *step = window->findChild<QQuickItem *>(QLatin1String(name));
        QVERIFY2(rowFit(step, QString::fromLatin1(name)).isEmpty(),
                 qPrintable(rowFit(step, QString::fromLatin1(name))));
    }

    const QString lineWords = QStringLiteral("a spoken line that is long enough to fill the row");
    QQuickItem *lineText = onScreen(lineWords);
    QVERIFY2(fullyInside(lineText, QStringLiteral("line")).isEmpty(),
             qPrintable(fullyInside(lineText, QStringLiteral("line"))));

    window->setProperty("currentLine", 30);
    QTest::qWait(50);
    QQuickItem *keep = visibleItemWithText(window, QStringLiteral("Keep"));
    QVERIFY(keep);
    QVERIFY(keep->isEnabled());
    QVERIFY(keep->opacity() > 0.5);
    QQuickItem *droppedRow = lineRowItem(keep);
    QVERIFY(droppedRow);
    QVERIFY(qAbs(droppedRow->opacity() - 1.0) < 0.01);
    window->setProperty("currentLine", 0);
    QTest::qWait(20);

    QQuickItem *render = visibleItemWithText(window, QStringLiteral("Render"));
    QVERIFY2(fullyInside(render, QStringLiteral("Render")).isEmpty(),
             qPrintable(fullyInside(render, QStringLiteral("Render"))));
    QVERIFY2(labelFitError(window, QStringLiteral("Render")).isEmpty(),
             qPrintable(labelFitError(window, QStringLiteral("Render"))));

    QQuickItem *shots = window->findChild<QQuickItem *>(QStringLiteral("shotsStep"));
    QVERIFY(shots);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shots));
    QTest::qWait(50);
    QVERIFY(visibleTextStartsWith(window, QStringLiteral("Keep each moment")));

    const QString paceLabel = QStringLiteral("Open \u00B7 keeps long pauses");
    QQuickItem *pace = visibleItemWithText(window, paceLabel);
    QVERIFY2(fullyInside(pace, paceLabel).isEmpty(), qPrintable(fullyInside(pace, paceLabel)));
    QQuickItem *paceField = window->findChild<QQuickItem *>(QStringLiteral("paceField"));
    QVERIFY(paceField);
    QVERIFY(!paceField->property("open").toBool());
    QCOMPARE(backend.moveCount, 0);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(pace));
    QTest::qWait(50);
    QVERIFY(paceField->property("open").toBool());
    // Alt+Down moves a shot only while the pace list is closed. Plain Down does not.
    QTest::keyClick(window, Qt::Key_Down, Qt::AltModifier);
    QCOMPARE(backend.moveCount, 0);
    QVERIFY(paceField->property("open").toBool());
    QCOMPARE(backend.pace(), QStringLiteral("open"));
    QTest::keyClick(window, Qt::Key_Escape);
    QTest::qWait(20);
    QVERIFY(!paceField->property("open").toBool());
    QTest::keyClick(window, Qt::Key_Down, Qt::AltModifier);
    QCOMPARE(backend.moveCount, 1);
    QCOMPARE(backend.lastMoveDelta, 1);
    for (const QString &label : {QStringLiteral("Save list\u2026"), QStringLiteral("Add a title card\u2026"),
                                 QStringLiteral("Add shots\u2026"), QStringLiteral("Lists")}) {
        QVERIFY2(fullyInside(visibleItemWithText(window, label), label).isEmpty(),
                 qPrintable(fullyInside(visibleItemWithText(window, label), label)));
        QVERIFY2(labelFitError(window, label).isEmpty(), qPrintable(labelFitError(window, label)));
    }
    // An open list shows its own actions. Opening another list starts from the home.
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Open a saved list\u2026")));
    QVERIFY(window->findChild<QQuickItem *>(QStringLiteral("settingsButton"))->isVisible());

    QQuickItem *addCard = visibleItemWithText(window, QStringLiteral("Add a title card\u2026"));
    QVERIFY(addCard);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(addCard));
    QTest::qWait(50);
    QQuickItem *cardField = window->findChild<QQuickItem *>(QStringLiteral("titleCardField"));
    QVERIFY(cardField);
    QVERIFY(cardField->isVisible());
    QCOMPARE(cardField->property("text").toString(), QString());
    QVERIFY2(fullyInside(visibleItemWithText(window, QStringLiteral("Put it first")),
                         QStringLiteral("Put it first"))
                 .isEmpty(),
             qPrintable(fullyInside(visibleItemWithText(window, QStringLiteral("Put it first")),
                                    QStringLiteral("Put it first"))));
    QVERIFY2(fullyInside(visibleItemWithText(window, QStringLiteral("Put it last")),
                         QStringLiteral("Put it last"))
                 .isEmpty(),
             qPrintable(fullyInside(visibleItemWithText(window, QStringLiteral("Put it last")),
                                    QStringLiteral("Put it last"))));
    QTest::keyClick(window, Qt::Key_Escape);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("titleCardOpen").toBool(), false, 3000);

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(settings));
    QCOMPARE(window->property("settingsOpen").toBool(), true);
    // Fade is the switch in the cut row and nowhere else.
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Fade to black between shots")));

    QQuickItem *spoken = window->findChild<QQuickItem *>(QStringLiteral("spokenCutsBox"));
    QVERIFY(spoken);
    QVERIFY(spoken->isVisible());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(spoken));
    QCOMPARE(backend.cutMode(), QStringLiteral("assemble"));
    QVERIFY(!visibleTextStartsWith(window, QStringLiteral("Keep each moment")));
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(spoken));
    QCOMPARE(backend.cutMode(), QStringLiteral("speech"));
    QVERIFY(visibleTextStartsWith(window, QStringLiteral("Keep each moment")));

    QTest::keyClick(window, Qt::Key_Escape);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("settingsOpen").toBool(), false, 3000);

    QQuickItem *linesStep = window->findChild<QQuickItem *>(QStringLiteral("linesStep"));
    QVERIFY(linesStep);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(linesStep));
    QTest::qWait(50);
    reviseField = window->findChild<QQuickItem *>(QStringLiteral("reviseField"));
    QVERIFY(reviseField && reviseField->isVisible());
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Send")));
    QCOMPARE(reviseField->setProperty("text", QStringLiteral("drop the stumble")), true);
    QTest::qWait(20);
    QQuickItem *reviseSend = window->findChild<QQuickItem *>(QStringLiteral("reviseSend"));
    QVERIFY(reviseSend);
    QVERIFY(reviseSend->isVisible());
    backend.setChat({ShortcutBackend::turn(QStringLiteral("you"), QStringLiteral("drop the stumble")),
                     ShortcutBackend::turn(QStringLiteral("bot"), QStringLiteral("Done."),
                                           QStringLiteral("Dropped 1 line."))},
                    false);
    backend.setCanRevert(true);
    QTest::qWait(50);
    QQuickItem *undo = visibleItemWithText(window, QStringLiteral("Undo"));
    QVERIFY(undo);
    QVERIFY(undo->isEnabled());

    backend.setBusy(true);
    QTest::qWait(50);
    QVERIFY(!reviseField->isEnabled());
    QVERIFY(!reviseSend->isVisible());
    QVERIFY(!undo->isVisible());

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shots));
    QTest::qWait(50);
    QVERIFY(paceField->isVisible());
    QVERIFY(!paceField->property("open").toBool());
    QQuickItem *paceHit = window->findChild<QQuickItem *>(QStringLiteral("paceHit"));
    QVERIFY(paceHit);
    QVERIFY(paceHit->isVisible());
    // MouseArea keeps its own enabled flag. QQuickItem::isEnabled() does not read it.
    QVERIFY(!paceHit->property("enabled").toBool());
    QQuickItem *cardButton = visibleItemWithText(window, QStringLiteral("Add a title card\u2026"));
    QVERIFY(cardButton);
    QVERIFY(!cardButton->isEnabled());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(paceHit));
    QTest::qWait(50);
    QVERIFY(!paceField->property("open").toBool());

    QQuickItem *home = window->findChild<QQuickItem *>(QStringLiteral("listsHome"));
    QVERIFY(home);
    QVERIFY(home->isVisible());
    QVERIFY(!home->isEnabled());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(home));
    QCOMPARE(backend.closeCount, 0);

    backend.setBusy(false);
    QTest::qWait(50);
    QVERIFY(home->isEnabled());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(home));
    QTest::qWait(50);
    QCOMPARE(backend.closeCount, 1);
    QVERIFY(backend.tray().isEmpty());
    QVERIFY(!home->isVisible());
    QVERIFY(visibleItemWithText(window, QStringLiteral("Pick up where you left off")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Send")));
    for (const QString &label : {QStringLiteral("Open a saved list…"), QStringLiteral("Add shots…")}) {
        QVERIFY2(fullyInside(visibleItemWithText(window, label), label).isEmpty(),
                 qPrintable(fullyInside(visibleItemWithText(window, label), label)));
        QVERIFY2(labelFitError(window, label).isEmpty(), qPrintable(labelFitError(window, label)));
    }
    QVERIFY(settings->isVisible());
    QVERIFY2(fullyInside(settings, QStringLiteral("Settings")).isEmpty(),
             qPrintable(fullyInside(settings, QStringLiteral("Settings"))));
}

void BackendTests::planFadeSwitchWritesSceneTransition() {
    ShortcutBackend backend(QUrl(), 0.0);
    backend.setTray({QStringLiteral("/tmp/shot.mp4")});
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("text"), QStringLiteral("We started in the garage."));
    backend.setSelects({line});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));
    QCOMPARE(window->findChildren<QQuickItem *>(QStringLiteral("planFadeSwitch")).size(), 1);

    QQuickItem *fade = window->findChild<QQuickItem *>(QStringLiteral("planFadeSwitch"));
    QVERIFY(fade);
    QVERIFY(fade->isVisible());
    QVERIFY(fade->width() > 10.0);
    QCOMPARE(fade->property("checked").toBool(), true);

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(fade));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("off"));
    QCOMPARE(fade->property("checked").toBool(), false);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(fade));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));
    QCOMPARE(fade->property("checked").toBool(), true);

    QQuickItem *settings = window->findChild<QQuickItem *>(QStringLiteral("settingsButton"));
    QVERIFY(settings);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(settings));
    QCOMPARE(window->property("settingsOpen").toBool(), true);
    // Settings has no second Fade control to fall out of step with this one.
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Fade to black between shots")));

    QTest::keyClick(window, Qt::Key_Escape);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("settingsOpen").toBool(), false, 3000);
    QQuickItem *shots = window->findChild<QQuickItem *>(QStringLiteral("shotsStep"));
    QVERIFY(shots);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shots));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    QVERIFY(fade->isVisible());
    QCOMPARE(fade->property("checked").toBool(), true);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(fade));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("off"));
    QCOMPARE(fade->property("checked").toBool(), false);
}

void BackendTests::linesPaceIsTheShotsPace() {
    ShortcutBackend backend(QUrl(), 0.0);
    backend.setTray({QStringLiteral("/tmp/shot.mp4")});
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("text"), QStringLiteral("We started in the garage."));
    backend.setSelects({line});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QCOMPARE(window->findChildren<QQuickItem *>(QStringLiteral("paceField")).size(), 1);

    const QString openPace = QStringLiteral("Open \u00B7 keeps long pauses");
    const QString tightPace = QStringLiteral("Tight \u00B7 trims most pauses");
    const QString measuredPace = QStringLiteral("Measured \u00B7 natural pauses");
    QList<QQuickItem *> copies;
    collectVisibleText(window->contentItem(), openPace, &copies);
    QCOMPARE(copies.size(), 1);

    QQuickItem *field = window->findChild<QQuickItem *>(QStringLiteral("paceField"));
    QVERIFY(field);
    QVERIFY(field->isVisible());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(copies.first()));
    QTest::qWait(50);
    QQuickItem *tight = visibleItemWithText(window, tightPace);
    QVERIFY(tight);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(tight));
    QCOMPARE(backend.pace(), QStringLiteral("tight"));
    QVERIFY(!field->property("open").toBool());

    QQuickItem *shots = window->findChild<QQuickItem *>(QStringLiteral("shotsStep"));
    QVERIFY(shots);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shots));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    QVERIFY(field->isVisible());
    copies.clear();
    collectVisibleText(window->contentItem(), tightPace, &copies);
    QCOMPARE(copies.size(), 1);
    QCOMPARE(backend.pace(), QStringLiteral("tight"));

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(copies.first()));
    QTest::qWait(50);
    QQuickItem *measured = visibleItemWithText(window, measuredPace);
    QVERIFY(measured);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(measured));
    QCOMPARE(backend.pace(), QStringLiteral("measured"));

    QQuickItem *lines = window->findChild<QQuickItem *>(QStringLiteral("linesStep"));
    QVERIFY(lines);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(lines));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QVERIFY(field->isVisible());
    copies.clear();
    collectVisibleText(window->contentItem(), measuredPace, &copies);
    QCOMPARE(copies.size(), 1);
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
}

void BackendTests::paceListKeysAndHide() {
    ShortcutBackend backend(QUrl(), 1.0);
    backend.setPlanCut(true);
    backend.setTray({QStringLiteral("/tmp/shot.mp4")});
    QVariantMap first;
    first.insert(QStringLiteral("id"), 1);
    first.insert(QStringLiteral("keep"), true);
    first.insert(QStringLiteral("text"), QStringLiteral("We started in the garage."));
    QVariantMap second;
    second.insert(QStringLiteral("id"), 2);
    second.insert(QStringLiteral("keep"), true);
    second.insert(QStringLiteral("text"), QStringLiteral("Then we opened the second location."));
    backend.setSelects({first, second});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->requestActivate();
    window->resize(960, 640);
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QCOMPARE(window->property("settingsOpen").toBool(), false);
    QCOMPARE(window->property("currentLine").toInt(), 0);

    QQuickItem *field = window->findChild<QQuickItem *>(QStringLiteral("paceField"));
    QVERIFY(field);
    QVERIFY(field->isVisible());
    QVERIFY(!field->property("open").toBool());

    // removeClip ignores a one-block film, so a trim would not show.
    QList<PlanFilm::Segment> segments;
    PlanFilm::Segment head;
    head.clip = 0;
    head.path = QStringLiteral("/tmp/shot.mp4");
    head.fileDuration = 60;
    head.start = 10;
    head.end = 14;
    PlanFilm::Segment tail = head;
    tail.start = 20;
    tail.end = 24;
    segments.append(head);
    segments.append(tail);
    backend.planFilm.load(segments);
    QQuickItem *editBar = window->findChild<QQuickItem *>(QStringLiteral("editBar"));
    QVERIFY(editBar);
    editBar->setProperty("playheadSec", 0.0);
    QCOMPARE(editBar->property("playheadSec").toDouble(), 0.0);
    QCOMPARE(backend.planFilm.segments().size(), 2);
    QCOMPARE(backend.planFilm.clipAt(0.0), 0);
    const QVariantList blocks = backend.planFilm.clipList();
    QTest::keyClick(window, Qt::Key_Delete);
    QCOMPARE(backend.lastDropId, -1);
    QCOMPARE(backend.lastRestoreId, -1);
    QCOMPARE(backend.planFilm.clipList(), blocks);
    QCOMPARE(backend.planFilm.segments().size(), 2);
    QTest::keyClick(window, Qt::Key_X);
    QCOMPARE(backend.lastDropId, 1);
    QCOMPARE(backend.planFilm.clipList(), blocks);
    QTest::keyClick(window, Qt::Key_Down);
    QCOMPARE(window->property("currentLine").toInt(), 1);
    QTest::keyClick(window, Qt::Key_Backspace);
    QCOMPARE(backend.lastDropId, 2);
    QCOMPARE(backend.planFilm.clipList(), blocks);

    QQuickItem *closed = nullptr;
    const auto kids = field->childItems();
    for (QQuickItem *child : kids) {
        if (child->property("activeFocusOnTab").toBool())
            closed = child;
    }
    QVERIFY(closed);
    closed->forceActiveFocus();
    QVERIFY(closed->hasActiveFocus());
    QTest::keyClick(window, Qt::Key_Return);
    QCOMPARE(field->property("open").toBool(), true);
    QCOMPARE(window->property("currentLine").toInt(), 1);
    QTest::keyClick(window, Qt::Key_Down);
    QCOMPARE(window->property("currentLine").toInt(), 1);
    QTest::keyClick(window, Qt::Key_Return);
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
    QVERIFY(!field->property("open").toBool());

    closed->forceActiveFocus();
    QVERIFY(closed->hasActiveFocus());
    QTest::keyClick(window, Qt::Key_Return);
    QCOMPARE(field->property("open").toBool(), true);

    // A click anywhere else closes the list. The field stays where it is.
    QQuickItem *shots = window->findChild<QQuickItem *>(QStringLiteral("shotsStep"));
    QVERIFY(shots);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shots));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    QCOMPARE(field->property("open").toBool(), false);
    QVERIFY(field->isVisible());

    QQuickItem *lines = window->findChild<QQuickItem *>(QStringLiteral("linesStep"));
    QVERIFY(lines);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(lines));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QCOMPARE(field->property("open").toBool(), false);
    QVERIFY(field->isVisible());

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shots));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    QCOMPARE(field->property("open").toBool(), false);
    QCOMPARE(window->property("settingsOpen").toBool(), false);

    backend.setPreviewUrl(QUrl::fromLocalFile(m_videoPath));
    QTest::qWait(50);
    QCOMPARE(window->property("previewing").toBool(), true);
    QObject *space = nullptr;
    const auto objects = window->findChildren<QObject *>();
    for (QObject *object : objects) {
        if (object->property("sequence").toString() == QStringLiteral("Space"))
            space = object;
    }
    QVERIFY(space);
    // The list closed with the step click and let the field's focus go, so Space plays.
    QCOMPARE(space->property("enabled").toBool(), true);
    closed->forceActiveFocus();
    QVERIFY(closed->hasActiveFocus());
    QCOMPARE(space->property("enabled").toBool(), false);
    QTest::keyClick(window, Qt::Key_Return);
    QCOMPARE(field->property("open").toBool(), true);
    QTest::keyClick(window, Qt::Key_Escape);
    QCOMPARE(field->property("open").toBool(), false);
    QTest::qWait(20);
    QVERIFY(!closed->hasActiveFocus());
    QCOMPARE(space->property("enabled").toBool(), true);

    backend.setCutMode(QStringLiteral("assemble"));
    QTest::qWait(50);
    QVERIFY(!field->isVisible());
    QQuickItem *cutRow = field->parentItem()->parentItem();
    QVERIFY(cutRow);
    QVERIFY(!cutRow->isVisible());
    QVERIFY(!field->property("open").toBool());
    QCOMPARE(space->property("enabled").toBool(), true);

    // Lines keeps the block when spoken cuts are off. Shots does not.
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(lines));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QCOMPARE(backend.cutMode(), QStringLiteral("assemble"));
    QVERIFY(field->isVisible());
    QVERIFY(!field->property("open").toBool());
    QVERIFY(cutRow->isVisible());
    // No sentence well without spoken cuts; the pace and the fade stay.
    QVERIFY(!visibleItemWithText(window, defaultCutIntent()));
    QCOMPARE(space->property("enabled").toBool(), true);

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shots));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    QVERIFY(!field->isVisible());
    QVERIFY(!cutRow->isVisible());
    QVERIFY(!field->property("open").toBool());

    backend.setCutMode(QStringLiteral("speech"));
    QTRY_VERIFY_WITH_TIMEOUT(field->isVisible(), 1000);
    QTRY_VERIFY_WITH_TIMEOUT(cutRow->isVisible(), 1000);
    QVERIFY(visibleItemWithText(window, defaultCutIntent()));

    closed->forceActiveFocus();
    QVERIFY(closed->hasActiveFocus());
    QTest::keyClick(window, Qt::Key_Return);
    QCOMPARE(field->property("open").toBool(), true);
    QCOMPARE(space->property("enabled").toBool(), false);

    backend.setSource(QUrl::fromLocalFile(m_videoPath));
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("movie"));
    QVERIFY(backend.planCut());
    QVERIFY(!field->isVisible());
    QVERIFY(!field->property("open").toBool());
    QCOMPARE(space->property("enabled").toBool(), true);
}

void BackendTests::showFileOpensTheSavedFolder() {
    struct FooterButton {
        qreal x = 0;
        QString text;
        bool filled = false;
    };
    const auto footerButtons = [](QQuickWindow *window) {
        QList<FooterButton> rows;
        const auto items = window->findChildren<QQuickItem *>();
        for (QQuickItem *item : items) {
            if (!item->isVisible() || !item->property("filled").isValid())
                continue;
            const QString text = item->property("text").toString();
            if (text.isEmpty())
                continue;
            rows.append(FooterButton{item->mapToScene(QPointF(0, 0)).x(), text,
                                     item->property("filled").toBool()});
        }
        std::sort(rows.begin(), rows.end(), [](const FooterButton &a, const FooterButton &b) {
            return a.x < b.x;
        });
        return rows;
    };
    const auto labelsOf = [&footerButtons](QQuickWindow *window) {
        QStringList labels;
        for (const FooterButton &row : footerButtons(window))
            labels.append(row.text);
        return labels;
    };

    const QString movie = m_dir.filePath(QStringLiteral("founder-story.mp4"));
    {
        ShortcutBackend backend(QUrl::fromLocalFile(movie), 10.0);
        backend.setRoughCut(true);
        QmlHarness harness(backend);
        QQuickWindow *window = harness.window();
        QVERIFY2(window, qPrintable(mainQmlPath()));
        window->show();
        window->resize(960, 640);
        QTest::qWait(50);
        QCOMPARE(window->property("displayStep").toString(), QStringLiteral("movieSaved"));
        const QList<FooterButton> rows = footerButtons(window);
        QStringList labels;
        for (const FooterButton &row : rows)
            labels.append(row.text);
        QCOMPARE(labels, (QStringList{QStringLiteral("Show the file"), QStringLiteral("Captions"),
                                      QStringLiteral("Vertical short"),
                                      QStringLiteral("Export another size…")}));
        for (const FooterButton &row : rows)
            QVERIFY(!row.filled);
        QVERIFY(!visibleItemWithText(window, QStringLiteral("Export…")));
        QCOMPARE(backend.shownDirectory, QString());
        QQuickItem *showFile = window->findChild<QQuickItem *>(QStringLiteral("showFileButton"));
        QVERIFY(showFile);
        QVERIFY(showFile->isVisible());
        QCOMPARE(showFile->property("filled").toBool(), false);
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(showFile));
        QCOMPARE(backend.shownDirectory, QFileInfo(movie).absolutePath());
        QVERIFY(backend.shownDirectory != movie);
        QCOMPARE(QFileInfo(movie).fileName(), QStringLiteral("founder-story.mp4"));
    }
    {
        ShortcutBackend backend(QUrl::fromLocalFile(movie), 10.0);
        backend.setRoughCut(true);
        backend.setRenderedUnsaved(true);
        QmlHarness harness(backend);
        QQuickWindow *window = harness.window();
        QVERIFY2(window, qPrintable(mainQmlPath()));
        window->show();
        window->resize(960, 640);
        QTest::qWait(50);
        QCOMPARE(window->property("displayStep").toString(), QStringLiteral("movieUnsaved"));
        const QList<FooterButton> rows = footerButtons(window);
        QCOMPARE(labelsOf(window), (QStringList{QStringLiteral("Save…")}));
        QCOMPARE(rows.size(), 1);
        QVERIFY(rows.first().filled);
        QVERIFY(!window->findChild<QQuickItem *>(QStringLiteral("showFileButton"))->isVisible());
    }
    {
        ShortcutBackend backend(QUrl::fromLocalFile(movie), 10.0);
        backend.setRoughCut(true);
        backend.timeline.setClip(0, 0.0, 5.0);
        QVERIFY(backend.timeline.unexported());
        QmlHarness harness(backend);
        QQuickWindow *window = harness.window();
        QVERIFY2(window, qPrintable(mainQmlPath()));
        window->show();
        window->resize(960, 640);
        QTest::qWait(50);
        QCOMPARE(window->property("displayStep").toString(), QStringLiteral("trimmed"));
        const QList<FooterButton> rows = footerButtons(window);
        QCOMPARE(labelsOf(window), (QStringList{QStringLiteral("Export…")}));
        QCOMPARE(rows.size(), 1);
        QVERIFY(rows.first().filled);
        QVERIFY(!window->findChild<QQuickItem *>(QStringLiteral("showFileButton"))->isVisible());
    }
    {
        ShortcutBackend backend(QUrl::fromLocalFile(movie), 10.0);
        QmlHarness harness(backend);
        QQuickWindow *window = harness.window();
        QVERIFY2(window, qPrintable(mainQmlPath()));
        window->show();
        window->resize(960, 640);
        QTest::qWait(50);
        QCOMPARE(window->property("displayStep").toString(), QStringLiteral("movieSaved"));
        QVERIFY(!backend.roughCut());
        const QList<FooterButton> rows = footerButtons(window);
        QCOMPARE(labelsOf(window), (QStringList{QStringLiteral("Export…")}));
        QCOMPARE(rows.size(), 1);
        QVERIFY(rows.first().filled);
        QVERIFY(!window->findChild<QQuickItem *>(QStringLiteral("showFileButton"))->isVisible());
    }
}

void BackendTests::showFileOpensTheParentDirectory() {
    RecordedOpen sink;
    QDesktopServices::setUrlHandler(QStringLiteral("file"), &sink, "open");
    struct Guard {
        ~Guard() { QDesktopServices::unsetUrlHandler(QStringLiteral("file")); }
    } guard;

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);

    backend.m_source = QUrl();
    backend.showFile();
    QCOMPARE(sink.urls.size(), 0);

    backend.m_source = QUrl::fromLocalFile(m_videoPath);
    backend.showFile();
    QCOMPARE(sink.urls.size(), 1);
    const QString path = backend.m_source.toLocalFile();
    QCOMPARE(sink.urls.first(), QUrl::fromLocalFile(QFileInfo(path).absolutePath()));
    QVERIFY(sink.urls.first() != QUrl::fromLocalFile(path));
    QCOMPARE(QFileInfo(path).fileName(), QStringLiteral("clip.mp4"));
}

void BackendTests::exportQualityNamesTheSourceSize() {
    const auto optionsOf = [](const QVariantMap &choice) {
        QList<QPair<QString, QString>> rows;
        const QVariantList list = choice.value(QStringLiteral("options")).toList();
        for (const QVariant &value : list) {
            const QVariantMap row = value.toMap();
            rows.append(qMakePair(row.value(QStringLiteral("id")).toString(),
                                  row.value(QStringLiteral("label")).toString()));
        }
        return rows;
    };

    {
        RecordingPortal picker;
        picker.exportVideo(QUrl::fromLocalFile(QStringLiteral("/tmp/wide.mp4")), {1080, 720}, 3840,
                           2160);
        QCOMPARE(picker.requests, 1);
        QCOMPARE(picker.method, QStringLiteral("SaveFile"));
        QCOMPARE(picker.options.value(QStringLiteral("accept_label")).toString(),
                 QStringLiteral("Export"));
        const QVariantMap choice = picker.quality();
        QCOMPARE(choice.value(QStringLiteral("id")).toString(), QStringLiteral("quality"));
        QCOMPARE(choice.value(QStringLiteral("label")).toString(), QStringLiteral("Quality"));
        QCOMPARE(choice.value(QStringLiteral("initial")).toString(), QStringLiteral("original"));
        const QList<QPair<QString, QString>> rows = optionsOf(choice);
        QCOMPARE(rows.size(), 3);
        QCOMPARE(rows.at(0).first, QStringLiteral("original"));
        QCOMPARE(rows.at(0).second, QStringLiteral("3840 x 2160 (original)"));
        QVERIFY(rows.at(0).second != QStringLiteral("Original"));
        QCOMPARE(rows.at(1).first, QStringLiteral("1080"));
        QCOMPARE(rows.at(1).second, QStringLiteral("1080p"));
        QCOMPARE(rows.at(2).first, QStringLiteral("720"));
        QCOMPARE(rows.at(2).second, QStringLiteral("720p"));
    }
    {
        // Not exportHeights(3840, 2160). A picker that ignores the list and recomputes adds 1080p.
        RecordingPortal picker;
        const QList<int> only720{720};
        QVERIFY(only720 != Backend::exportHeights(3840, 2160));
        picker.exportVideo(QUrl::fromLocalFile(QStringLiteral("/tmp/wide-720.mp4")), only720, 3840,
                           2160);
        const QList<QPair<QString, QString>> rows = optionsOf(picker.quality());
        QCOMPARE(rows.size(), 2);
        QCOMPARE(rows.at(0).first, QStringLiteral("original"));
        QCOMPARE(rows.at(0).second, QStringLiteral("3840 x 2160 (original)"));
        QCOMPARE(rows.at(1).first, QStringLiteral("720"));
        QCOMPARE(rows.at(1).second, QStringLiteral("720p"));
        for (const auto &row : rows)
            QVERIFY(row.second != QStringLiteral("1080p"));
    }
    {
        RecordingPortal picker;
        picker.exportVideo(QUrl::fromLocalFile(QStringLiteral("/tmp/hd.mp4")), {720}, 1920, 1080);
        const QList<QPair<QString, QString>> rows = optionsOf(picker.quality());
        QCOMPARE(rows.size(), 2);
        QCOMPARE(rows.at(0).first, QStringLiteral("original"));
        QCOMPARE(rows.at(0).second, QStringLiteral("1920 x 1080 (original)"));
        QCOMPARE(rows.at(1).first, QStringLiteral("720"));
        QCOMPARE(rows.at(1).second, QStringLiteral("720p"));
    }
    {
        RecordingPortal picker;
        const QList<int> none = Backend::exportHeights(1280, 720);
        QCOMPARE(none, QList<int>{});
        picker.exportVideo(QUrl::fromLocalFile(QStringLiteral("/tmp/small.mp4")), none, 1280, 720);
        QCOMPARE(picker.requests, 1);
        QVERIFY(!picker.options.contains(QStringLiteral("choices")));
        QVERIFY(picker.quality().isEmpty());
        QCOMPARE(picker.options.value(QStringLiteral("accept_label")).toString(),
                 QStringLiteral("Export"));
    }
}

void BackendTests::lineRowDropStaysOnTheUnselectedRow() {
    ShortcutBackend backend(QUrl(), 0.0);
    const QString garage = QStringLiteral("We started in the garage.");
    const QString second = QStringLiteral("Then we opened the second location.");
    const QString shops = QStringLiteral("The first customers were shops on the same street.");
    QVariantMap first;
    first.insert(QStringLiteral("id"), 1);
    first.insert(QStringLiteral("keep"), true);
    first.insert(QStringLiteral("text"), garage);
    first.insert(QStringLiteral("start"), 12.0);
    first.insert(QStringLiteral("end"), 15.0);
    first.insert(QStringLiteral("clip"), 0);
    QVariantMap next;
    next.insert(QStringLiteral("id"), 2);
    next.insert(QStringLiteral("keep"), true);
    next.insert(QStringLiteral("text"), second);
    next.insert(QStringLiteral("start"), 88.0);
    next.insert(QStringLiteral("end"), 91.0);
    next.insert(QStringLiteral("clip"), 0);
    QVariantMap dropped;
    dropped.insert(QStringLiteral("id"), 3);
    dropped.insert(QStringLiteral("keep"), false);
    dropped.insert(QStringLiteral("text"), shops);
    dropped.insert(QStringLiteral("clip"), 0);
    QVariantMap cover;
    cover.insert(QStringLiteral("clip"), 0);
    cover.insert(QStringLiteral("line"), 3);
    backend.setTray({QStringLiteral("/tmp/shot.mp4")});
    backend.setTrayIndex(0);
    backend.setCutClips({QStringLiteral("/cuts/room.mp4")});
    backend.setCovers({cover});
    backend.setSelects({first, next, dropped});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    QVERIFY(window->contentItem());
    window->show();
    window->requestActivate();
    window->resize(960, 640);
    QTest::qWait(50);
    QTest::mouseMove(window, QPoint(1, 1));
    QCOMPARE(window->property("currentLine").toInt(), 0);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));

    const auto sentenceRow = [&](const QString &sentence) -> QQuickItem * {
        QList<QQuickItem *> found;
        collectVisibleText(window->contentItem(), sentence, &found);
        return found.isEmpty() ? nullptr : lineRowItem(found.first());
    };
    const auto wordsOn = [&](QQuickItem *row, const QString &word) {
        QList<QQuickItem *> found;
        if (row)
            collectVisibleText(row, word, &found);
        return found;
    };
    QTRY_VERIFY_WITH_TIMEOUT(sentenceRow(garage) && sentenceRow(second) && sentenceRow(shops), 3000);
    QQuickItem *garageRow = sentenceRow(garage);
    QQuickItem *secondRow = sentenceRow(second);
    QQuickItem *shopsRow = sentenceRow(shops);
    QVERIFY(garageRow->property("selected").toBool());
    QVERIFY(!secondRow->property("selected").toBool());
    QVERIFY(!shopsRow->property("selected").toBool());
    const auto oneWord = [](const QList<QQuickItem *> &found) -> QQuickItem * {
        return found.size() == 1 ? found.first() : nullptr;
    };
    const QColor accent = window->property("accent").value<QColor>();
    QVERIFY(accent.isValid());
    const auto filled = [&](QQuickItem *label) {
        if (!label || !label->parentItem())
            return false;
        const QColor color = label->parentItem()->property("color").value<QColor>();
        return qAbs(color.red() - accent.red()) <= 1 && qAbs(color.green() - accent.green()) <= 1
               && qAbs(color.blue() - accent.blue()) <= 1 && color.alpha() > 200;
    };
    const auto inForce = [](QQuickItem *label) {
        return label && label->parentItem() && label->parentItem()->property("active").toBool();
    };
    // One word on every row: Drop on a kept line, Keep on a dropped one. It is
    // the only control on a row that is not selected.
    QQuickItem *garageDrop = oneWord(wordsOn(garageRow, QStringLiteral("Drop")));
    QQuickItem *secondDrop = oneWord(wordsOn(secondRow, QStringLiteral("Drop")));
    QQuickItem *shopsKeep = oneWord(wordsOn(shopsRow, QStringLiteral("Keep")));
    QVERIFY(garageDrop);
    QVERIFY(secondDrop);
    QVERIFY(shopsKeep);
    QVERIFY(wordsOn(garageRow, QStringLiteral("Keep")).isEmpty());
    QVERIFY(wordsOn(secondRow, QStringLiteral("Keep")).isEmpty());
    QVERIFY(wordsOn(shopsRow, QStringLiteral("Drop")).isEmpty());
    QVERIFY(!filled(garageDrop));
    QVERIFY(!filled(shopsKeep));
    // The word's pill, the row's layout, the body column, then the row.
    QCOMPARE(lineRowItem(secondDrop), secondRow);
    QCOMPARE(window->property("currentLine").toInt(), 0);

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(garageDrop));
    QCOMPARE(backend.lastDropId, 1);
    QCOMPARE(backend.lastRestoreId, -1);
    QTRY_VERIFY_WITH_TIMEOUT(
        sentenceRow(garage) && sentenceRow(garage)->property("dropped").toBool(), 3000);
    garageRow = sentenceRow(garage);
    QQuickItem *garageKeep = oneWord(wordsOn(garageRow, QStringLiteral("Keep")));
    QVERIFY(garageKeep);
    QVERIFY(wordsOn(garageRow, QStringLiteral("Drop")).isEmpty());
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(garageKeep));
    QCOMPARE(backend.lastRestoreId, 1);
    QCOMPARE(backend.lastDropId, -1);
    QTRY_VERIFY_WITH_TIMEOUT(
        sentenceRow(garage) && !sentenceRow(garage)->property("dropped").toBool(), 3000);

    // The unselected dropped row flips without becoming the current line.
    shopsRow = sentenceRow(shops);
    shopsKeep = oneWord(wordsOn(shopsRow, QStringLiteral("Keep")));
    QVERIFY(shopsKeep);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shopsKeep));
    QCOMPARE(backend.lastRestoreId, 3);
    QCOMPARE(backend.lastDropId, -1);
    QTRY_VERIFY_WITH_TIMEOUT(
        sentenceRow(shops) && !sentenceRow(shops)->property("dropped").toBool(), 3000);
    shopsRow = sentenceRow(shops);
    QQuickItem *shopsDrop = oneWord(wordsOn(shopsRow, QStringLiteral("Drop")));
    QVERIFY(shopsDrop);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(shopsDrop));
    QCOMPARE(backend.lastDropId, 3);
    QCOMPARE(backend.lastRestoreId, -1);
    QTRY_VERIFY_WITH_TIMEOUT(
        sentenceRow(shops) && sentenceRow(shops)->property("dropped").toBool(), 3000);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    QCOMPARE(window->property("currentLine").toInt(), 0);
    garageRow = sentenceRow(garage);
    secondRow = sentenceRow(second);
    shopsRow = sentenceRow(shops);
    QVERIFY(garageRow);
    QVERIFY(secondRow);
    QVERIFY(shopsRow);
    QVERIFY(garageRow->property("selected").toBool());

    QList<QQuickItem *> plays;
    collectVisibleText(window->contentItem(), QStringLiteral("Play"), &plays);
    QCOMPARE(plays.size(), 1);
    QCOMPARE(lineRowItem(plays.first()), garageRow);
    QVERIFY(plays.first()->opacity() > 0.5);

    const edit::Clips clips = backend.timeline.clips();
    QTest::keyClick(window, Qt::Key_Up);
    QCOMPARE(window->property("currentLine").toInt(), 0);
    QCOMPARE(window->property("linePlayStart").toInt(), -1);
    QCOMPARE(window->property("linePlayEnd").toInt(), -1);
    QCOMPARE(window->property("lineHold").toBool(), false);
    QCOMPARE(window->property("linePreview").toBool(), false);
    QCOMPARE(backend.timeline.clips(), clips);

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(plays.first()));
    QCOMPARE(window->property("linePreview").toBool(), true);
    QCOMPARE(window->property("lineHold").toBool(), false);

    QTest::keyClick(window, Qt::Key_X);
    QCOMPARE(backend.lastDropId, 1);
    QCOMPARE(backend.lastRestoreId, -1);
    QCOMPARE(backend.timeline.clips(), clips);

    QTest::keyClick(window, Qt::Key_Down);
    QCOMPARE(window->property("currentLine").toInt(), 1);
    QCOMPARE(window->property("lineHold").toBool(), true);
    QCOMPARE(window->property("linePreview").toBool(), false);
    QCOMPARE(window->property("linePlayStart").toInt(), 88000);
    QCOMPARE(window->property("linePlayEnd").toInt(), 91000);
    QCOMPARE(backend.timeline.clips(), clips);

    const int heldStart = window->property("linePlayStart").toInt();
    const int heldEnd = window->property("linePlayEnd").toInt();
    const bool heldHold = window->property("lineHold").toBool();
    const bool heldPreview = window->property("linePreview").toBool();
    QTest::keyClick(window, Qt::Key_Down);
    QCOMPARE(window->property("currentLine").toInt(), 2);
    QCOMPARE(window->property("linePlayStart").toInt(), heldStart);
    QCOMPARE(window->property("linePlayEnd").toInt(), heldEnd);
    QCOMPARE(window->property("lineHold").toBool(), heldHold);
    QCOMPARE(window->property("linePreview").toBool(), heldPreview);

    QTest::keyClick(window, Qt::Key_Backspace);
    QCOMPARE(backend.lastDropId, 1);
    QCOMPARE(backend.lastRestoreId, 3);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    QTest::keyClick(window, Qt::Key_Delete);
    QCOMPARE(backend.lastDropId, -1);
    QCOMPARE(backend.lastRestoreId, -1);
    QCOMPARE(backend.timeline.clips(), clips);

    QList<QQuickItem *> shopLines;
    collectVisibleText(window->contentItem(), shops, &shopLines);
    QQuickItem *shopLine = nullptr;
    for (QQuickItem *item : shopLines) {
        if (lineRowItem(item)) {
            shopLine = item;
            break;
        }
    }
    QVERIFY(shopLine);
    // Restored, so this is the kept look. 0.38 and strikeout are the dropped line.
    QVERIFY(!QQmlProperty::read(shopLine, QStringLiteral("font.strikeout")).toBool());
    QVERIFY(qAbs(shopLine->opacity() - 1.0) < 0.01);
    plays.clear();
    collectVisibleText(window->contentItem(), QStringLiteral("Play"), &plays);
    QCOMPARE(plays.size(), 1);
    // dropSelect rebuilds the rows, so the pointer taken before X is gone.
    shopsRow = lineRowItem(shopLine);
    QVERIFY(shopsRow);
    QCOMPARE(lineRowItem(plays.first()), shopsRow);
    QVERIFY(plays.first()->opacity() > 0.5);

    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    // X is the one key for Drop and Keep. K and D do nothing.
    QTest::keyClick(window, Qt::Key_K);
    QTest::keyClick(window, Qt::Key_D);
    QCOMPARE(backend.lastDropId, -1);
    QCOMPARE(backend.lastRestoreId, -1);
    QTest::keyClick(window, Qt::Key_X);
    QCOMPARE(backend.lastDropId, 3);
    QCOMPARE(backend.lastRestoreId, -1);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    QTest::keyClick(window, Qt::Key_X);
    QCOMPARE(backend.lastDropId, -1);
    QCOMPARE(backend.lastRestoreId, 3);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;

    backend.setBusy(true);
    QTest::qWait(20);
    QList<QQuickItem *> drops;
    QList<QQuickItem *> keeps;
    collectVisibleText(window->contentItem(), QStringLiteral("Drop"), &drops);
    collectVisibleText(window->contentItem(), QStringLiteral("Keep"), &keeps);
    QCOMPARE(drops.size() + keeps.size(), 3);
    for (QQuickItem *item : drops)
        QVERIFY(qAbs(item->opacity() - 0.38) < 0.01);
    for (QQuickItem *item : keeps)
        QVERIFY(qAbs(item->opacity() - 0.38) < 0.01);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    secondRow = sentenceRow(second);
    QVERIFY(secondRow);
    QCOMPARE(wordsOn(secondRow, QStringLiteral("Drop")).size(), 1);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier,
                      itemCenter(wordsOn(secondRow, QStringLiteral("Drop")).first()));
    QCOMPARE(backend.lastDropId, -1);
    QCOMPARE(backend.lastRestoreId, -1);
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    QTest::keyClick(window, Qt::Key_X);
    QCOMPARE(backend.lastDropId, -1);
    QCOMPARE(backend.lastRestoreId, -1);
    QCOMPARE(backend.covers().size(), 1);
    QList<QQuickItem *> removeBroll;
    collectVisibleText(window->contentItem(), QStringLiteral("Remove B-roll"), &removeBroll);
    QCOMPARE(removeBroll.size(), 1);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(removeBroll.first()));
    QCOMPARE(backend.covers().size(), 1);
    QCOMPARE(backend.timeline.clips(), clips);

    backend.setBusy(false);
    QTest::qWait(20);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(removeBroll.first()));
    QCOMPARE(backend.covers().size(), 0);
    QCOMPARE(backend.timeline.clips(), clips);

    // A focused chat field keeps Ctrl+R and the line keys to itself.
    QQuickItem *chatField = window->findChild<QQuickItem *>(QStringLiteral("reviseField"));
    QVERIFY(chatField);
    chatField->forceActiveFocus();
    QVERIFY(chatField->hasActiveFocus());
    QVERIFY(window->property("controlFocused").toBool());
    backend.lastDropId = -1;
    backend.lastRestoreId = -1;
    const int rendersWhileTyping = backend.renderCount;
    QTest::keyClick(window, Qt::Key_X);
    QCOMPARE(backend.lastDropId, -1);
    QTest::keyClick(window, Qt::Key_R, Qt::ControlModifier);
    QCOMPARE(backend.renderCount, rendersWhileTyping);
    // The window content item is a focus scope, so it would hand focus back to the field.
    chatField->parentItem()->parentItem()->forceActiveFocus();
    QVERIFY(!chatField->hasActiveFocus());
    QVERIFY(!window->property("controlFocused").toBool());
    QTest::keyClick(window, Qt::Key_R, Qt::ControlModifier);
    QCOMPARE(backend.renderCount, rendersWhileTyping + 1);
}

void BackendTests::reviseChatStates() {
    ShortcutBackend backend(QUrl(), 0.0);
    QVariantMap line;
    line.insert(QStringLiteral("id"), 7);
    line.insert(QStringLiteral("text"), QStringLiteral("pricing"));
    line.insert(QStringLiteral("keep"), true);
    backend.setSelects({line});
    backend.m_acceptRevise = true;

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    QTest::qWait(50);

    const auto clickSend = [&](const QString &note) {
        QQuickItem *field = window->findChild<QQuickItem *>(QStringLiteral("reviseField"));
        QVERIFY(field);
        QVERIFY(field->setProperty("text", note));
        QTest::qWait(20);
        QQuickItem *send = window->findChild<QQuickItem *>(QStringLiteral("reviseSend"));
        QVERIFY(send);
        QVERIFY(send->isVisible());
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(send));
        QTest::qWait(20);
    };
    QQuickItem *field = window->findChild<QQuickItem *>(QStringLiteral("reviseField"));
    QVERIFY(field);
    QVERIFY(field->isVisible());
    QVERIFY(visibleItemWithText(window, QStringLiteral("Ask for a change…")));

    // A note that gets no reply comes back to the field.
    clickSend(QStringLiteral("bring back the pricing"));
    QCOMPARE(backend.lastRevise, QStringLiteral("bring back the pricing"));
    QCOMPARE(field->property("text").toString(), QString());
    backend.setBusy(true);
    QTest::qWait(20);
    QVERIFY(visibleItemWithText(window, QStringLiteral("Thinking…")));
    QVERIFY(!field->isEnabled());
    backend.setBusy(false);
    QTest::qWait(50);
    QCOMPARE(field->property("text").toString(), QStringLiteral("bring back the pricing"));
    QVERIFY(visibleItemWithText(
        window, QStringLiteral("That change didn't go through. Your note is back in the field.")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Thinking…")));

    // A reply is a proposal. Nothing moves until Apply.
    clickSend(QStringLiteral("drop the pricing part"));
    backend.setBusy(true);
    backend.setChat({ShortcutBackend::turn(QStringLiteral("you"), QStringLiteral("drop the pricing part")),
                     ShortcutBackend::turn(QStringLiteral("bot"), QStringLiteral("I'd drop the pricing line."),
                                           QStringLiteral("Drops 1 line. New movie sentence. Pace becomes Tight."))},
                    true);
    QTest::qWait(20);
    backend.setBusy(false);
    QTest::qWait(50);
    QVERIFY(visibleItemWithText(window, QStringLiteral("drop the pricing part")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("I'd drop the pricing line.")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("Drops 1 line. New movie sentence. Pace becomes Tight.")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("Say yes, or ask for something else")));
    QQuickItem *apply = visibleItemWithText(window, QStringLiteral("Apply"));
    QVERIFY(apply);
    QVERIFY(visibleItemWithText(window, QStringLiteral("Leave it")));
    QCOMPARE(backend.applyCount, 0);
    QCOMPARE(backend.renderCount, 0);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(apply));
    QTest::qWait(20);
    QCOMPARE(backend.applyCount, 1);
    backend.setBusy(true);
    QTest::qWait(20);
    QVERIFY(visibleItemWithText(window, QStringLiteral("Applying…")));
    QVariantMap dropped = line;
    dropped.insert(QStringLiteral("keep"), false);
    backend.setSelects({dropped});
    backend.setPace(QStringLiteral("tight"));
    backend.setIntent(QStringLiteral("A tighter movie."));
    QVariantList turns = backend.chat();
    turns.append(ShortcutBackend::turn(QStringLiteral("bot"), QStringLiteral("Done."),
                                       QStringLiteral("Dropped 1 line. New movie sentence. Pace is now Tight.")));
    backend.setChat(turns, false);
    backend.setCanRevert(true);
    backend.setBusy(false);
    QTest::qWait(50);
    QVERIFY(visibleItemWithText(window, QStringLiteral("Done.")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("Dropped 1 line. New movie sentence. Pace is now Tight.")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Apply")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Applying…")));
    QQuickItem *undo = visibleItemWithText(window, QStringLiteral("Undo"));
    QVERIFY(undo);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(undo));
    QTest::qWait(20);
    QVERIFY(visibleItemWithText(window, QStringLiteral("Undone. Back to how it was before this note.")));
    QVERIFY(!backend.canRevert());
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Undo")));

    backend.setCanRevert(true);
    backend.m_revertWorks = false;
    QTest::qWait(20);
    undo = visibleItemWithText(window, QStringLiteral("Undo"));
    QVERIFY(undo);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(undo));
    QTest::qWait(20);
    QVERIFY(visibleItemWithText(window, QStringLiteral("Could not undo. The line list did not save.")));
    QVERIFY(backend.canRevert());

    // A typed yes is Apply. Anything else is a new note.
    turns.append(ShortcutBackend::turn(QStringLiteral("bot"), QStringLiteral("Shall I tighten it?"),
                                       QStringLiteral("Pace becomes Frenzied.")));
    backend.setChat(turns, true);
    QTest::qWait(20);
    backend.lastRevise.clear();
    clickSend(QStringLiteral("Yes, do it."));
    QCOMPARE(backend.applyCount, 2);
    QCOMPARE(backend.lastRevise, QString());
    clickSend(QStringLiteral("no, make it shorter"));
    QCOMPARE(backend.applyCount, 2);
    QCOMPARE(backend.lastRevise, QStringLiteral("no, make it shorter"));

    // Leave it drops the proposal and keeps the thread.
    backend.setChat(turns, true);
    QTest::qWait(20);
    QQuickItem *leave = visibleItemWithText(window, QStringLiteral("Leave it"));
    QVERIFY(leave);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(leave));
    QTest::qWait(20);
    QCOMPARE(backend.dismissCount, 1);
    QVERIFY(!backend.proposalPending());
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Apply")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("Shall I tighten it?")));
}

void BackendTests::reviseFromMovieOpensLines() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("movie.mp4"))), 10.0);
    backend.setPlanCut(true);
    QVariantMap line;
    line.insert(QStringLiteral("id"), 3);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("text"), QStringLiteral("garage"));
    backend.setSelects({line});
    backend.setTray({QStringLiteral("/tmp/one.mp4")});
    backend.m_acceptRevise = true;

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("movie"));

    QQuickItem *field = window->findChild<QQuickItem *>(QStringLiteral("reviseField"));
    QVERIFY(field);
    QVERIFY(field->isVisible());

    const auto clickSend = [&](const QString &note) {
        QVERIFY(field->setProperty("text", note));
        QTest::qWait(20);
        QQuickItem *send = window->findChild<QQuickItem *>(QStringLiteral("reviseSend"));
        QVERIFY(send);
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(send));
        QTest::qWait(20);
    };

    // A reply that changes nothing stays on Movie.
    clickSend(QStringLiteral("leave it"));
    backend.setBusy(true);
    backend.setChat({ShortcutBackend::turn(QStringLiteral("you"), QStringLiteral("leave it")),
                     ShortcutBackend::turn(QStringLiteral("bot"), QStringLiteral("It stays as it is."),
                                           QStringLiteral("Nothing would change."))},
                    false);
    backend.setBusy(false);
    QTest::qWait(50);
    QCOMPARE(backend.showShotsCount, 0);
    QVERIFY(visibleItemWithText(window, QStringLiteral("Nothing would change.")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Apply")));
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("movie"));

    // An applied change returns to Lines.
    clickSend(QStringLiteral("drop it"));
    backend.setBusy(true);
    QVariantList turns = backend.chat();
    turns.append(ShortcutBackend::turn(QStringLiteral("you"), QStringLiteral("drop it")));
    turns.append(ShortcutBackend::turn(QStringLiteral("bot"), QStringLiteral("Dropping the garage line."),
                                       QStringLiteral("Drops 1 line.")));
    backend.setChat(turns, true);
    backend.setBusy(false);
    QTest::qWait(50);
    QCOMPARE(backend.showShotsCount, 0);
    QQuickItem *apply = visibleItemWithText(window, QStringLiteral("Apply"));
    QVERIFY(apply);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(apply));
    QTest::qWait(20);
    QCOMPARE(backend.applyCount, 1);
    backend.setBusy(true);
    QVariantMap dropped = line;
    dropped.insert(QStringLiteral("keep"), false);
    backend.setSelects({dropped});
    turns.append(ShortcutBackend::turn(QStringLiteral("bot"), QStringLiteral("Done."), QStringLiteral("Dropped 1 line.")));
    backend.setChat(turns, false);
    backend.setBusy(false);
    QTest::qWait(50);
    QCOMPARE(backend.showShotsCount, 1);
}

void BackendTests::listsAsksBeforeLeavingAHandTrim() {
    {
        ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("plain.mp4"))), 10.0);
        backend.setTray({QStringLiteral("/tmp/one.mp4")});
        QmlHarness harness(backend);
        QQuickWindow *window = harness.window();
        QVERIFY2(window, qPrintable(mainQmlPath()));
        window->show();
        QTest::qWait(50);
        QVERIFY(!window->property("unexported").toBool());
        QQuickItem *home = window->findChild<QQuickItem *>(QStringLiteral("listsHome"));
        QVERIFY(home);
        QVERIFY(home->isVisible());
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(home));
        QTest::qWait(50);
        QCOMPARE(backend.closeCount, 1);
        QVERIFY(!window->property("quitConfirmVisible").toBool());
    }
    {
        ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("trim.mp4"))), 10.0);
        backend.setTray({QStringLiteral("/tmp/one.mp4")});
        backend.timeline.setClip(0, 0.0, 5.0);
        QVERIFY(backend.timeline.unexported());
        QmlHarness harness(backend);
        QQuickWindow *window = harness.window();
        QVERIFY2(window, qPrintable(mainQmlPath()));
        window->show();
        window->resize(960, 640);
        QTest::qWait(80);
        QVERIFY(window->property("unexported").toBool());

        const QString sentence = QStringLiteral(
            "Trimmed by hand. Export writes a new file. Captions and the short wait until then.");
        QQuickItem *footer = visibleItemWithText(window, sentence);
        QVERIFY(footer);
        QVERIFY(footer->isVisible());
        QCOMPARE(footer->property("elide").toInt(), static_cast<int>(Qt::ElideNone));
        // QQuickText::WordWrap, not Qt::TextWordWrap.
        QCOMPARE(footer->property("wrapMode").toInt(), 1);
        QVERIFY(footer->height() + 1.0 >= footer->implicitHeight());

        QQuickItem *home = window->findChild<QQuickItem *>(QStringLiteral("listsHome"));
        QVERIFY(home);
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(home));
        QTest::qWait(50);
        QCOMPARE(backend.closeCount, 0);
        QVERIFY(window->property("quitConfirmVisible").toBool());
        QVERIFY(visibleItemWithText(window, QStringLiteral("Export your trim before you go to Lists?")));
        QVERIFY(!window->property("quitting").toBool());

        QQuickItem *keep = dialogButton(window, QStringLiteral("Keep working"));
        QVERIFY(keep);
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(keep));
        QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), false, 3000);
        QCOMPARE(backend.closeCount, 0);

        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(home));
        QTest::qWait(50);
        QQuickItem *exportButton = dialogButton(window, QStringLiteral("Export\u2026"));
        QVERIFY(exportButton);
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(exportButton));
        QTest::qWait(50);
        QCOMPARE(backend.closeCount, 0);
        QCOMPARE(backend.exportCount, 1);
        QVERIFY(!window->property("quitConfirmVisible").toBool());

        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(home));
        QTest::qWait(50);
        QQuickItem *go = dialogButton(window, QStringLiteral("Go to Lists without exporting"));
        QVERIFY(go);
        QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(go));
        QTest::qWait(50);
        QCOMPARE(backend.closeCount, 1);
        QVERIFY(!window->property("quitting").toBool());
        QVERIFY(window->isVisible());
    }
}

void BackendTests::closeProjectKeepsTheFiles() {
    const QString movie = makeVideo(QStringLiteral("close-project.mp4"), 2.0, false);
    QVERIFY(!movie.isEmpty());
    const QString cuts = m_dir.filePath(QStringLiteral("close-project-cuts.json"));
    {
        QFile file(cuts);
        QVERIFY(file.open(QIODevice::WriteOnly));
        file.write("{}");
    }

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.addTrayFiles({movie});
    const QString list = m_dir.filePath(QStringLiteral("close-project.botcut.json"));
    backend.writeCutListFile(QUrl::fromLocalFile(list));
    QVERIFY(QFileInfo(list).isFile());
    QVERIFY(backend.load(QUrl::fromLocalFile(movie)));
    QVERIFY(!backend.gathering());
    const int lists = backend.recentLists().size();
    QVERIFY(lists > 0);

    backend.m_busy = true;
    backend.closeProject();
    QVERIFY(!backend.gathering());
    QCOMPARE(backend.tray().size(), 1);
    backend.m_busy = false;

    QSignalSpy gathering(&backend, &Backend::gatheringChanged);
    QSignalSpy tray(&backend, &Backend::trayChanged);
    backend.closeProject();
    QVERIFY(backend.gathering());
    QCOMPARE(gathering.count(), 1);
    QVERIFY(tray.count() > 0);
    QVERIFY(backend.tray().isEmpty());
    QCOMPARE(backend.trayIndex(), -1);
    QVERIFY(backend.selects().isEmpty());
    QVERIFY(backend.source().isEmpty());
    QCOMPARE(backend.duration(), 0.0);
    QVERIFY(!backend.planCut());
    QVERIFY(!backend.renderedUnsaved());
    QCOMPARE(backend.step(), QStringLiteral("empty"));
    QVERIFY(!backend.busy());
    QCOMPARE(backend.recentLists().size(), lists);
    QVERIFY(QFileInfo(movie).isFile());
    QVERIFY(QFileInfo(list).isFile());
    QVERIFY(QFileInfo(cuts).isFile());
}

void BackendTests::linePlayReachedEnd() {
    QFile file(QFileInfo(QString::fromUtf8(__FILE__)).dir().absoluteFilePath(
        QStringLiteral("../src/Format.js")));
    QVERIFY(file.open(QIODevice::ReadOnly));
    QString src = QString::fromUtf8(file.readAll());
    src.remove(QStringLiteral(".pragma library"));
    QJSEngine engine;
    const QJSValue loaded = engine.evaluate(src);
    QVERIFY2(!loaded.isError(), qPrintable(loaded.toString()));

    QCOMPARE(engine.evaluate(QStringLiteral("linePlayReachedEnd(1000, 5000, 8000, true)")).toBool(), false);
    QCOMPARE(engine.evaluate(QStringLiteral("linePlayReachedEnd(8000, 5000, 8000, true)")).toBool(), true);
    QCOMPARE(engine.evaluate(QStringLiteral("linePlayReachedEnd(6500, 5000, 8000, true)")).toBool(), false);
    QCOMPARE(engine.evaluate(QStringLiteral("linePlayReachedEnd(9000, 5000, 8000, true)")).toBool(), true);
    QCOMPARE(engine.evaluate(QStringLiteral("linePlayReachedEnd(8000, 5000, 8000, false)")).toBool(), false);
}

void BackendTests::nextKeptAir() {
    QFile file(QFileInfo(QString::fromUtf8(__FILE__)).dir().absoluteFilePath(
        QStringLiteral("../src/Format.js")));
    QVERIFY(file.open(QIODevice::ReadOnly));
    QString src = QString::fromUtf8(file.readAll());
    src.remove(QStringLiteral(".pragma library"));
    QJSEngine engine;
    const QJSValue loaded = engine.evaluate(src);
    QVERIFY2(!loaded.isError(), qPrintable(loaded.toString()));

    const auto run = [&](const QString &call) {
        return engine.evaluate(call);
    };

    // Gap longer than the pace plays only the pace. Returning the whole gap fails.
    const QJSValue wide = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:true,start:12,end:14}], 0, 0.4)"));
    QVERIFY2(!wide.isError(), qPrintable(wide.toString()));
    QCOMPARE(wide.property(QStringLiteral("air")).toNumber(), 0.4);
    QCOMPARE(wide.property(QStringLiteral("next")).toInt(), 1);

    // Gap shorter than the pace plays as it is. Always returning the pace fails.
    const QJSValue narrow = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:true,start:10.2,end:12}], 0, 0.4)"));
    QVERIFY2(!narrow.isError(), qPrintable(narrow.toString()));
    QCOMPARE(narrow.property(QStringLiteral("air")).toNumber(), 0.2);
    QCOMPARE(narrow.property(QStringLiteral("next")).toInt(), 1);

    // Equal to the pace plays the pace. Treating equality as no air fails.
    const QJSValue equalPace = run(QStringLiteral("2.4 - 2"));
    const QJSValue equal = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:2},{clip:0,keep:true,start:2.4,end:4}], 0, 2.4 - 2)"));
    QVERIFY2(!equal.isError(), qPrintable(equal.toString()));
    QCOMPARE(equal.property(QStringLiteral("air")).toNumber(), equalPace.toNumber());
    QVERIFY(equal.property(QStringLiteral("air")).toNumber() != 0.0);
    QCOMPARE(equal.property(QStringLiteral("next")).toInt(), 1);

    // A cap hardcoded at 0.4 returns 0.4 here, and returning the whole gap returns 2.
    const QJSValue openPace = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:true,start:12,end:14}], 0, 0.8)"));
    QVERIFY2(!openPace.isError(), qPrintable(openPace.toString()));
    QCOMPARE(openPace.property(QStringLiteral("air")).toNumber(), 0.8);
    QVERIFY(openPace.property(QStringLiteral("air")).toNumber() != 0.4);
    QVERIFY(openPace.property(QStringLiteral("air")).toNumber() != 2.0);
    QCOMPARE(openPace.property(QStringLiteral("next")).toInt(), 1);

    // Always playing the gap returns 0.2. The pace is the cap.
    const QJSValue frenzied = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:true,start:10.2,end:12}], 0, 0.1)"));
    QVERIFY2(!frenzied.isError(), qPrintable(frenzied.toString()));
    QCOMPARE(frenzied.property(QStringLiteral("air")).toNumber(), 0.1);
    QVERIFY(frenzied.property(QStringLiteral("air")).toNumber() != 0.2);
    QCOMPARE(frenzied.property(QStringLiteral("next")).toInt(), 1);

    // A different file plays nothing, even when the numeric gap is the short one.
    const QJSValue otherFile = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:1,keep:true,start:10.2,end:12}], 0, 0.4)"));
    QVERIFY2(!otherFile.isError(), qPrintable(otherFile.toString()));
    QCOMPARE(otherFile.property(QStringLiteral("air")).toNumber(), 0.0);
    QCOMPARE(otherFile.property(QStringLiteral("next")).toInt(), 1);

    // The dropped line between them is not the next line, and its 0.1s gap is not the air.
    const QJSValue skipped = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},"
        "{clip:0,keep:false,start:10.1,end:11},"
        "{clip:0,keep:true,start:20,end:23}], 0, 0.4)"));
    QVERIFY2(!skipped.isError(), qPrintable(skipped.toString()));
    QCOMPARE(skipped.property(QStringLiteral("air")).toNumber(), 0.4);
    QCOMPARE(skipped.property(QStringLiteral("next")).toInt(), 2);

    // A follower that omits keep is kept. Requiring keep === true skips it and lands on index 2.
    const QJSValue omittedKeep = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},"
        "{clip:0,start:12,end:14},"
        "{clip:0,keep:true,start:30,end:32}], 0, 0.4)"));
    QVERIFY2(!omittedKeep.isError(), qPrintable(omittedKeep.toString()));
    QCOMPARE(omittedKeep.property(QStringLiteral("air")).toNumber(), 0.4);
    QCOMPARE(omittedKeep.property(QStringLiteral("next")).toInt(), 1);

    // Nothing kept follows: stop. Do not play air.
    const QJSValue none = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10}], 0, 0.4)"));
    QVERIFY2(!none.isError(), qPrintable(none.toString()));
    QVERIFY(none.isNull());
    const QJSValue droppedOnly = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:false,start:12,end:14}], 0, 0.4)"));
    QVERIFY2(!droppedOnly.isError(), qPrintable(droppedOnly.toString()));
    QVERIFY(droppedOnly.isNull());
    const QJSValue noEnd = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:true,start:12}], 0, 0.4)"));
    QVERIFY2(!noEnd.isError(), qPrintable(noEnd.toString()));
    QVERIFY(noEnd.isNull());
    // Halting on a missing end returns null. Skipping it reaches the later line.
    // Air is the gap from this line to that later line, capped by the pace.
    const QJSValue skipEnd = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},"
        "{clip:0,keep:true,start:11},"
        "{clip:0,keep:true,start:12,end:14}], 0, 0.4)"));
    QVERIFY2(!skipEnd.isError(), qPrintable(skipEnd.toString()));
    QVERIFY(!skipEnd.isNull());
    QCOMPARE(skipEnd.property(QStringLiteral("air")).toNumber(), 0.4);
    QCOMPARE(skipEnd.property(QStringLiteral("next")).toInt(), 2);
    // A rule that only rejects a missing end keeps the middle line. It has an end and no start.
    const QJSValue skipStart = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},"
        "{clip:0,keep:true,end:11.5},"
        "{clip:0,keep:true,start:10.2,end:12}], 0, 0.4)"));
    QVERIFY2(!skipStart.isError(), qPrintable(skipStart.toString()));
    QVERIFY(!skipStart.isNull());
    QCOMPARE(skipStart.property(QStringLiteral("air")).toNumber(), 0.2);
    QCOMPARE(skipStart.property(QStringLiteral("next")).toInt(), 2);

    // A touch or an overlap plays no air, and the next kept line still starts.
    const QJSValue touch = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:true,start:10,end:12}], 0, 0.4)"));
    QVERIFY2(!touch.isError(), qPrintable(touch.toString()));
    QCOMPARE(touch.property(QStringLiteral("air")).toNumber(), 0.0);
    QCOMPARE(touch.property(QStringLiteral("next")).toInt(), 1);
    const QJSValue overlap = run(QStringLiteral(
        "nextKeptAir([{clip:0,keep:true,start:0,end:10},{clip:0,keep:true,start:9.5,end:12}], 0, 0.4)"));
    QVERIFY2(!overlap.isError(), qPrintable(overlap.toString()));
    QCOMPARE(overlap.property(QStringLiteral("air")).toNumber(), 0.0);
    QCOMPARE(overlap.property(QStringLiteral("next")).toInt(), 1);
}

void BackendTests::cutRawWord() {
    ShortcutBackend backend(QUrl(), 0.0);
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("text"), QStringLiteral("We started in the garage."));
    line.insert(QStringLiteral("start"), 12.0);
    line.insert(QStringLiteral("end"), 15.0);
    line.insert(QStringLiteral("clip"), 0);
    backend.setTray({QStringLiteral("/tmp/shot.mp4")});
    backend.setTrayIndex(0);
    backend.setSelects({line});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->requestActivate();
    window->resize(960, 640);
    QTest::qWait(50);

    const auto chips = [window]() {
        return window->findChildren<QQuickItem *>(QStringLiteral("cutRawChip"));
    };
    const auto visibleChip = [&]() -> QQuickItem * {
        for (QQuickItem *item : chips()) {
            if (item->isVisible())
                return item;
        }
        return nullptr;
    };
    const auto labelOn = [](QQuickItem *chip, const QString &word) -> QQuickItem * {
        QList<QQuickItem *> found;
        if (chip)
            collectVisibleText(chip, word, &found);
        return found.size() == 1 ? found.first() : nullptr;
    };

    QTRY_VERIFY_WITH_TIMEOUT(visibleChip() != nullptr, 3000);
    QQuickItem *chip = visibleChip();
    QCOMPARE(chip->objectName(), QStringLiteral("cutRawChip"));
    QCOMPARE(chip->height(), 28.0);
    QQuickItem *cutWord = labelOn(chip, QStringLiteral("Cut"));
    QQuickItem *originalWord = labelOn(chip, QStringLiteral("Original"));
    QVERIFY(cutWord);
    QVERIFY(originalWord);
    QVERIFY(cutWord->parentItem() != chip);
    QVERIFY(originalWord->parentItem() != chip);
    QVERIFY(cutWord->parentItem()->property("active").toBool());
    QVERIFY(!originalWord->parentItem()->property("active").toBool());
    QCOMPARE(window->property("cutPreview").toBool(), true);
    QVERIFY(cutWord->opacity() > 0.9);
    QQuickItem *footer = window->findChild<QQuickItem *>(QStringLiteral("cutButton"));
    QVERIFY(footer);
    QVERIFY(footer->isVisible());
    QCOMPARE(footer->property("text").toString(), QStringLiteral("Render"));

    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(cutWord));
    QCOMPARE(window->property("cutPreview").toBool(), true);
    QVERIFY(cutWord->parentItem()->property("active").toBool());
    QVERIFY(!originalWord->parentItem()->property("active").toBool());
    QCOMPARE(footer->property("text").toString(), QStringLiteral("Render"));
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(originalWord));
    QCOMPARE(window->property("cutPreview").toBool(), false);
    QVERIFY(!cutWord->parentItem()->property("active").toBool());
    QVERIFY(originalWord->parentItem()->property("active").toBool());
    QCOMPARE(cutWord->property("text").toString(), QStringLiteral("Cut"));
    QCOMPARE(originalWord->property("text").toString(), QStringLiteral("Original"));
    QCOMPARE(footer->property("text").toString(), QStringLiteral("Render"));
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(cutWord));
    QCOMPARE(window->property("cutPreview").toBool(), true);
    QVERIFY(cutWord->parentItem()->property("active").toBool());
    QVERIFY(!originalWord->parentItem()->property("active").toBool());
    QCOMPARE(footer->property("text").toString(), QStringLiteral("Render"));

    QVERIFY(window->setProperty("shotsPinned", true));
    QTest::qWait(30);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    QVERIFY(!chips().isEmpty());
    for (QQuickItem *item : chips())
        QVERIFY(!item->isVisible());

    QVERIFY(window->setProperty("shotsPinned", false));
    backend.setCutMode(QStringLiteral("assemble"));
    backend.setSelects({});
    QTest::qWait(30);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    footer = window->findChild<QQuickItem *>(QStringLiteral("cutButton"));
    QVERIFY(footer);
    QVERIFY(footer->isVisible());
    QCOMPARE(footer->property("text").toString(), QStringLiteral("Cut"));
    QVERIFY(!chips().isEmpty());
    for (QQuickItem *item : chips())
        QVERIFY(!item->isVisible());

    backend.setCutMode(QStringLiteral("speech"));
    backend.setSelects({line});
    QTest::qWait(30);
    chip = visibleChip();
    QVERIFY(chip);
    cutWord = labelOn(chip, QStringLiteral("Cut"));
    originalWord = labelOn(chip, QStringLiteral("Original"));
    QVERIFY(cutWord);
    QVERIFY(originalWord);
    QVERIFY(cutWord->parentItem()->property("active").toBool());
    QCOMPARE(window->property("cutPreview").toBool(), true);
    backend.setBusy(true);
    QTest::qWait(30);
    QVERIFY(chip->isVisible());
    QVERIFY(qAbs(cutWord->opacity() - 0.38) < 0.01);
    QVERIFY(qAbs(originalWord->opacity() - 0.38) < 0.01);
    QCOMPARE(cutWord->property("text").toString(), QStringLiteral("Cut"));
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(originalWord));
    QCOMPARE(window->property("cutPreview").toBool(), true);
    QCOMPARE(cutWord->property("text").toString(), QStringLiteral("Cut"));
    QVERIFY(qAbs(cutWord->opacity() - 0.38) < 0.01);

    const auto visibleCount = [](QQuickWindow *watch) {
        int shown = 0;
        const auto items = watch->findChildren<QQuickItem *>(QStringLiteral("cutRawChip"));
        for (QQuickItem *item : items) {
            if (item->isVisible())
                ++shown;
        }
        return shown;
    };
    const auto onlyChip = [](QQuickWindow *watch) -> QQuickItem * {
        QQuickItem *found = nullptr;
        const auto items = watch->findChildren<QQuickItem *>(QStringLiteral("cutRawChip"));
        for (QQuickItem *item : items) {
            if (!item->isVisible())
                continue;
            if (found)
                return nullptr;
            found = item;
        }
        return found;
    };

    // The picture row is up, lines exist, and this is not a plan. A lines chip
    // that shows whenever there are lines is visible here.
    {
        ShortcutBackend watch(QUrl::fromLocalFile(QStringLiteral("/tmp/rough_cut.mp4")), 7.0);
        watch.setSelects({line});
        QVERIFY(!watch.gathering());
        QVERIFY(!watch.planCut());
        QmlHarness watchHarness(watch);
        QQuickWindow *watchWindow = watchHarness.window();
        QVERIFY(watchWindow);
        watchWindow->show();
        watchWindow->requestActivate();
        watchWindow->resize(960, 640);
        QTest::qWait(50);
        QCOMPARE(watchWindow->property("viewStep").toString(), QStringLiteral("movie"));
        QTRY_COMPARE_WITH_TIMEOUT(visibleCount(watchWindow), 0, 3000);
    }

    // Plan before the window is shown. The setter does not notify on its own.
    {
        ShortcutBackend watch(QUrl::fromLocalFile(QStringLiteral("/tmp/rough_cut.mp4")), 7.0);
        watch.setPlanCut(true);
        watch.setSelects({line});
        QVERIFY(watch.planCut());
        QmlHarness watchHarness(watch);
        QQuickWindow *watchWindow = watchHarness.window();
        QVERIFY(watchWindow);
        watchWindow->show();
        watchWindow->requestActivate();
        watchWindow->resize(960, 640);
        QTest::qWait(50);
        QCOMPARE(watchWindow->property("viewStep").toString(), QStringLiteral("movie"));
        QTRY_VERIFY_WITH_TIMEOUT(onlyChip(watchWindow) != nullptr, 3000);
        QQuickItem *movieChip = onlyChip(watchWindow);
        QVERIFY(movieChip);
        QCOMPARE(movieChip->objectName(), QStringLiteral("cutRawChip"));
        QCOMPARE(visibleCount(watchWindow), 1);
        QQuickItem *movieWord = labelOn(movieChip, QStringLiteral("Cut"));
        QVERIFY(movieWord);
        QCOMPARE(movieWord->property("text").toString(), QStringLiteral("Cut"));
        QVERIFY(movieWord->parentItem()->property("active").toBool());
        QVERIFY(labelOn(movieChip, QStringLiteral("Original")));
        QQuickItem *movieFooter = watchWindow->findChild<QQuickItem *>(QStringLiteral("cutButton"));
        QVERIFY(movieFooter);
        QVERIFY(movieChip != movieFooter);
        watch.setPlanCut(false);
        watch.announceInfo();
        QTest::qWait(30);
        QCOMPARE(visibleCount(watchWindow), 0);
    }
}

static QString sentencePlain(const QQuickItem *item) {
    if (!item)
        return {};
    QString joined;
    const auto kids = item->childItems();
    for (QQuickItem *child : kids) {
        if (!child->isVisible())
            continue;
        const QString part = child->property("text").toString();
        if (!part.isEmpty())
            joined += part;
    }
    if (!joined.isEmpty())
        return joined;
    QString text = item->property("text").toString();
    text.remove(QRegularExpression(QStringLiteral("<[^>]*>")));
    return text;
}

static bool itemIsUnder(QQuickItem *ancestor, QQuickItem *item) {
    for (QQuickItem *cursor = item; cursor; cursor = cursor->parentItem()) {
        if (cursor == ancestor)
            return true;
    }
    return false;
}

// findChildren misses these repeater delegates. They are visual children.
static void collectVisual(QQuickItem *item, QList<QQuickItem *> *out) {
    const auto kids = item->childItems();
    for (QQuickItem *child : kids) {
        out->append(child);
        collectVisual(child, out);
    }
}

static QQuickItem *visibleGap(QQuickItem *bar, int index) {
    if (!bar)
        return nullptr;
    QList<QQuickItem *> items;
    collectVisual(bar, &items);
    for (QQuickItem *item : items) {
        const QQmlProperty from(item, QStringLiteral("from"));
        const QQmlProperty dropped(item, QStringLiteral("droppedGap"));
        const QQmlProperty at(item, QStringLiteral("index"));
        if (!from.isValid() || !dropped.isValid() || !at.isValid())
            continue;
        if (at.read().toInt() != index || !item->isVisible() || item->width() <= 1.0)
            continue;
        return item;
    }
    return nullptr;
}

static QQuickItem *gapHoverArea(QQuickItem *bar) {
    QList<QQuickItem *> items;
    collectVisual(bar, &items);
    for (QQuickItem *item : items) {
        if (QQmlProperty(item, QStringLiteral("gapHovered")).isValid())
            return item;
    }
    return nullptr;
}

void BackendTests::pictureSentenceUnderThePicture() {
    ShortcutBackend backend(QUrl(), 0.0);
    backend.setPace(QStringLiteral("measured"));
    backend.setTray({QStringLiteral("/tmp/shot.mp4")});
    backend.setTrayIndex(0);

    QVariantMap first;
    first.insert(QStringLiteral("id"), 1);
    first.insert(QStringLiteral("keep"), true);
    first.insert(QStringLiteral("text"), QStringLiteral("We started in the garage."));
    first.insert(QStringLiteral("start"), 0.0);
    first.insert(QStringLiteral("end"), 3.0);
    first.insert(QStringLiteral("clip"), 0);
    // No keep key. Counting it as dropped would read 2 of 4 and 0:06.
    QVariantMap omitted;
    omitted.insert(QStringLiteral("id"), 2);
    omitted.insert(QStringLiteral("text"), QStringLiteral("Then we opened the second location."));
    omitted.insert(QStringLiteral("start"), 3.0);
    omitted.insert(QStringLiteral("end"), 7.0);
    omitted.insert(QStringLiteral("clip"), 0);
    QVariantMap third;
    third.insert(QStringLiteral("id"), 3);
    third.insert(QStringLiteral("keep"), true);
    third.insert(QStringLiteral("text"), QStringLiteral("Shops on the same street."));
    third.insert(QStringLiteral("start"), 7.0);
    third.insert(QStringLiteral("end"), 10.0);
    third.insert(QStringLiteral("clip"), 0);
    QVariantMap dropped;
    dropped.insert(QStringLiteral("id"), 4);
    dropped.insert(QStringLiteral("keep"), false);
    dropped.insert(QStringLiteral("text"), QStringLiteral("Cut this one."));
    dropped.insert(QStringLiteral("start"), 10.0);
    dropped.insert(QStringLiteral("end"), 14.0);
    dropped.insert(QStringLiteral("clip"), 0);
    backend.setSelects({first, omitted, third, dropped});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->requestActivate();
    window->resize(960, 640);
    QTest::qWait(50);

    // One sentence, in the action bar beside the filled button, says how much is kept.
    QQuickItem *sentence = window->findChild<QQuickItem *>(QStringLiteral("actionSentence"));
    QVERIFY(sentence);
    QTRY_VERIFY_WITH_TIMEOUT(sentence->isVisible(), 3000);
    const QString measured = QStringLiteral("3 of 4 lines kept, 0:10. Render makes the movie.");
    QTRY_COMPARE_WITH_TIMEOUT(sentence->property("text").toString(), measured, 3000);
    QCOMPARE(QQmlProperty::read(sentence, QStringLiteral("font.pixelSize")).toInt(), 13);
    QVERIFY(qAbs(sentence->opacity() - 0.62) < 0.01);
    QCOMPARE(window->width(), 960);
    QCOMPARE(window->height(), 640);
    const QPointF sentenceAt = sentence->mapToScene(QPointF(0, 0));
    QVERIFY2(sentenceAt.x() >= -0.5 && sentenceAt.y() >= -0.5
                 && sentenceAt.x() + sentence->width() <= window->width() + 1.0
                 && sentenceAt.y() + sentence->height() <= window->height() + 1.0,
             qPrintable(QStringLiteral("%1,%2 %3x%4")
                            .arg(sentenceAt.x())
                            .arg(sentenceAt.y())
                            .arg(sentence->width())
                            .arg(sentence->height())));

    QQuickItem *cut = window->findChild<QQuickItem *>(QStringLiteral("cutButton"));
    QVERIFY(cut);
    QQuickItem *actionBar = window->findChild<QQuickItem *>(QStringLiteral("actionBar"));
    QVERIFY(actionBar);
    QQuickItem *linesStep = window->findChild<QQuickItem *>(QStringLiteral("linesStep"));
    QVERIFY(linesStep);
    QVERIFY2(itemIsUnder(actionBar, sentence), "the sentence is outside the action bar");
    QVERIFY2(itemIsUnder(actionBar, cut), "the filled button is outside the action bar");
    QVERIFY2(!itemIsUnder(actionBar, linesStep), "the steps are in the action bar");
    // The button and its sentence sit on one line.
    QVERIFY(qAbs(cut->mapToScene(QPointF(0, cut->height() / 2)).y()
                 - sentence->mapToScene(QPointF(0, sentence->height() / 2)).y()) < 8.0);
    QVERIFY(cut->mapToScene(QPointF(0, 0)).x() > sentenceAt.x() + sentence->width() - 1.0);

    // The picture keeps most of the height. No inspector under it.
    QQuickItem *well = window->findChild<QQuickItem *>(QStringLiteral("pictureWell"));
    QVERIFY(well);
    QVERIFY2(well->height() >= 380.0, qPrintable(QString::number(well->height())));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Result")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Kept")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Click a block to show that line")));
    QQuickItem *timeline = window->findChild<QQuickItem *>(QStringLiteral("lineTimeline"));
    QVERIFY(timeline);
    QVERIFY(timeline->isVisible());
    QQuickItem *clock = window->findChild<QQuickItem *>(QStringLiteral("transportClock"));
    QVERIFY(clock);
    QVERIFY(clock->isVisible());
    QCOMPARE(clock->property("text").toString(), QStringLiteral("0:00 / 0:10"));

    // Shots has its own sentence. Lines has the count.
    QVERIFY(window->setProperty("shotsPinned", true));
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));
    QVERIFY(!timeline->isVisible());
    QVERIFY(window->setProperty("shotsPinned", false));
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QTRY_COMPARE_WITH_TIMEOUT(sentence->property("text").toString(), measured, 3000);

    backend.setPace(QStringLiteral("tight"));
    QCOMPARE(sentence->property("text").toString(), measured);
    QCOMPARE(backend.maxPause(), 1.0);

    const auto rowFor = [&](const QString &words) -> QQuickItem * {
        QList<QQuickItem *> found;
        collectVisibleText(window->contentItem(), words, &found);
        return found.isEmpty() ? nullptr : lineRowItem(found.first());
    };
    QTRY_VERIFY_WITH_TIMEOUT(rowFor(QStringLiteral("We started in the garage.")) != nullptr, 3000);
    QList<QQuickItem *> dropWords;
    collectVisibleText(rowFor(QStringLiteral("We started in the garage.")), QStringLiteral("Drop"), &dropWords);
    QCOMPARE(dropWords.size(), 1);
    backend.lastDropId = -1;
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(dropWords.first()));
    QCOMPARE(backend.lastDropId, 1);
    QTRY_COMPARE_WITH_TIMEOUT(sentence->property("text").toString(),
                              QStringLiteral("2 of 4 lines kept, 0:07. Render makes the movie."), 3000);
    QCOMPARE(clock->property("text").toString(), QStringLiteral("0:00 / 0:07"));

    QVariantMap only;
    only.insert(QStringLiteral("id"), 5);
    only.insert(QStringLiteral("keep"), true);
    only.insert(QStringLiteral("text"), QStringLiteral("Only one."));
    only.insert(QStringLiteral("start"), 0.0);
    only.insert(QStringLiteral("end"), 3.0);
    only.insert(QStringLiteral("clip"), 0);
    QVariantMap alsoDropped;
    alsoDropped.insert(QStringLiteral("id"), 6);
    alsoDropped.insert(QStringLiteral("keep"), false);
    alsoDropped.insert(QStringLiteral("text"), QStringLiteral("Left out."));
    alsoDropped.insert(QStringLiteral("start"), 3.0);
    alsoDropped.insert(QStringLiteral("end"), 7.0);
    alsoDropped.insert(QStringLiteral("clip"), 0);
    backend.setPace(QStringLiteral("measured"));
    backend.setSelects({only, alsoDropped});
    const QString oneLine = QStringLiteral("1 of 2 lines kept, 0:03. Render makes the movie.");
    QTRY_COMPARE_WITH_TIMEOUT(sentence->property("text").toString(), oneLine, 3000);

    // A line with no end has no clock. The count stays.
    QVariantMap hasEnd;
    hasEnd.insert(QStringLiteral("id"), 7);
    hasEnd.insert(QStringLiteral("keep"), true);
    hasEnd.insert(QStringLiteral("text"), QStringLiteral("Has an end."));
    hasEnd.insert(QStringLiteral("start"), 0.0);
    hasEnd.insert(QStringLiteral("end"), 5.0);
    hasEnd.insert(QStringLiteral("clip"), 0);
    QVariantMap noEnd;
    noEnd.insert(QStringLiteral("id"), 9);
    noEnd.insert(QStringLiteral("keep"), true);
    noEnd.insert(QStringLiteral("text"), QStringLiteral("No end."));
    noEnd.insert(QStringLiteral("start"), 10.0);
    noEnd.insert(QStringLiteral("clip"), 0);
    backend.setSelects({noEnd});
    QTRY_COMPARE_WITH_TIMEOUT(sentence->property("text").toString(),
                              QStringLiteral("1 of 1 lines kept. Render makes the movie."), 3000);
    backend.setSelects({hasEnd, noEnd});
    QTRY_COMPARE_WITH_TIMEOUT(sentence->property("text").toString(),
                              QStringLiteral("2 of 2 lines kept, 0:05. Render makes the movie."), 3000);

    QVariantMap allGone = only;
    allGone.insert(QStringLiteral("keep"), false);
    backend.setSelects({allGone});
    QTRY_COMPARE_WITH_TIMEOUT(sentence->property("text").toString(),
                              QStringLiteral("Every line is dropped. Keep one to render."), 3000);
    QVERIFY(!cut->isEnabled());

    backend.setSelects({});
    QTRY_VERIFY_WITH_TIMEOUT(!timeline->isVisible(), 3000);

    {
        ShortcutBackend watch(QUrl::fromLocalFile(QStringLiteral("/tmp/rough_cut.mp4")), 7.0);
        watch.setPace(QStringLiteral("measured"));
        watch.setSelects({only, alsoDropped});
        watch.setRenderedUnsaved(true);
        QmlHarness watchHarness(watch);
        QQuickWindow *watchWindow = watchHarness.window();
        QVERIFY(watchWindow);
        watchWindow->show();
        watchWindow->requestActivate();
        watchWindow->resize(960, 640);
        QTest::qWait(50);
        QCOMPARE(watchWindow->property("viewStep").toString(), QStringLiteral("movie"));
        QQuickItem *movieSentence = watchWindow->findChild<QQuickItem *>(QStringLiteral("actionSentence"));
        QVERIFY(movieSentence);
        QTRY_VERIFY_WITH_TIMEOUT(movieSentence->isVisible(), 3000);
        QCOMPARE(movieSentence->property("text").toString(),
                 QStringLiteral("Your movie is ready. It's only in a temporary folder until you save it."));
        QVERIFY(!watchWindow->findChild<QQuickItem *>(QStringLiteral("lineTimeline"))->isVisible());
    }
}

void BackendTests::planGapWashMarksADroppedLine() {
    ShortcutBackend backend(QUrl::fromLocalFile(QStringLiteral("/tmp/rough_cut.mp4")), 14.0);
    backend.setPlanCut(true);
    QList<PlanFilm::Segment> segments;
    const auto add = [&](double start, double end) {
        PlanFilm::Segment seg;
        seg.clip = 0;
        seg.path = QStringLiteral("/tmp/shot.mp4");
        seg.fileDuration = 60;
        seg.start = start;
        seg.end = end;
        segments.append(seg);
    };
    // Kept blocks with equal 4s holes between them, then a removed tail.
    add(50, 52); // stay
    add(20, 24); // dropped hole, gap 1
    add(10, 12); // stay
    add(0, 4);   // mixed hole, gap 2
    add(30, 32); // stay
    add(40, 42); // first span of the two-span hole, gap 3
    add(6, 8);   // pace air in that same hole
    add(34, 36); // stay, last kept block
    add(54, 58); // tail
    backend.planFilm.load(segments);
    backend.planFilm.removeClip(8);
    backend.planFilm.removeClip(6);
    backend.planFilm.removeClip(5);
    backend.planFilm.removeClip(3);
    backend.planFilm.removeClip(1);
    QCOMPARE(backend.planFilm.segments().size(), 4);
    QCOMPARE(backend.planFilm.duration(), 24.0);
    const QVariantList shown = backend.planFilm.clipList();
    QCOMPARE(shown.size(), 4);
    const QVariantList droppedHole = shown.at(1).toMap().value(QStringLiteral("holes")).toList();
    const QVariantList mixedHole = shown.at(2).toMap().value(QStringLiteral("holes")).toList();
    const QVariantList airHole = shown.at(3).toMap().value(QStringLiteral("holes")).toList();
    const QVariantList tail = shown.at(3).toMap().value(QStringLiteral("tail")).toList();
    QCOMPARE(droppedHole.size(), 1);
    QCOMPARE(droppedHole.at(0).toMap().value(QStringLiteral("clip")).toInt(), 0);
    QCOMPARE(droppedHole.at(0).toMap().value(QStringLiteral("start")).toDouble(), 20.0);
    QCOMPARE(droppedHole.at(0).toMap().value(QStringLiteral("end")).toDouble(), 24.0);
    QCOMPARE(mixedHole.size(), 1);
    QCOMPARE(mixedHole.at(0).toMap().value(QStringLiteral("start")).toDouble(), 0.0);
    QCOMPARE(mixedHole.at(0).toMap().value(QStringLiteral("end")).toDouble(), 4.0);
    QCOMPARE(airHole.size(), 2);
    QCOMPARE(airHole.at(0).toMap().value(QStringLiteral("start")).toDouble(), 40.0);
    QCOMPARE(airHole.at(0).toMap().value(QStringLiteral("end")).toDouble(), 42.0);
    QCOMPARE(airHole.at(1).toMap().value(QStringLiteral("start")).toDouble(), 6.0);
    QCOMPARE(airHole.at(1).toMap().value(QStringLiteral("end")).toDouble(), 8.0);
    QCOMPARE(tail.size(), 1);
    QCOMPARE(tail.at(0).toMap().value(QStringLiteral("clip")).toInt(), 0);
    QCOMPARE(tail.at(0).toMap().value(QStringLiteral("start")).toDouble(), 54.0);
    QCOMPARE(tail.at(0).toMap().value(QStringLiteral("end")).toDouble(), 58.0);
    QVERIFY(shown.at(0).toMap().value(QStringLiteral("tail")).toList().isEmpty());

    // Ends on the dropped hole's start. A closed overlap paints that hole black.
    QVariantMap endsOnHole;
    endsOnHole.insert(QStringLiteral("id"), 1);
    endsOnHole.insert(QStringLiteral("keep"), true);
    endsOnHole.insert(QStringLiteral("clip"), 0);
    endsOnHole.insert(QStringLiteral("start"), 16.0);
    endsOnHole.insert(QStringLiteral("end"), 20.0);
    endsOnHole.insert(QStringLiteral("text"), QStringLiteral("ends where the hole starts"));
    QVariantMap dropped;
    dropped.insert(QStringLiteral("id"), 2);
    dropped.insert(QStringLiteral("keep"), false);
    dropped.insert(QStringLiteral("clip"), 0);
    dropped.insert(QStringLiteral("start"), 20.0);
    dropped.insert(QStringLiteral("end"), 24.0);
    dropped.insert(QStringLiteral("text"), QStringLiteral("dropped line"));
    // Touches the dropped span only at its out point. A closed overlap paints that hole black.
    QVariantMap boundary;
    boundary.insert(QStringLiteral("id"), 3);
    boundary.insert(QStringLiteral("keep"), true);
    boundary.insert(QStringLiteral("clip"), 0);
    boundary.insert(QStringLiteral("start"), 24.0);
    boundary.insert(QStringLiteral("end"), 28.0);
    boundary.insert(QStringLiteral("text"), QStringLiteral("next line"));
    // Same times on another file. A clip-blind overlap paints the dropped hole black.
    QVariantMap otherFile;
    otherFile.insert(QStringLiteral("id"), 4);
    otherFile.insert(QStringLiteral("keep"), true);
    otherFile.insert(QStringLiteral("clip"), 1);
    otherFile.insert(QStringLiteral("start"), 20.0);
    otherFile.insert(QStringLiteral("end"), 24.0);
    otherFile.insert(QStringLiteral("text"), QStringLiteral("other file"));
    QVariantMap mixedDropped;
    mixedDropped.insert(QStringLiteral("id"), 5);
    mixedDropped.insert(QStringLiteral("keep"), false);
    mixedDropped.insert(QStringLiteral("clip"), 0);
    mixedDropped.insert(QStringLiteral("start"), 0.0);
    mixedDropped.insert(QStringLiteral("end"), 2.0);
    mixedDropped.insert(QStringLiteral("text"), QStringLiteral("dropped half"));
    // No keep key, and it shares the mixed span. Treating a missing keep as dropped paints that hole.
    QVariantMap omitted;
    omitted.insert(QStringLiteral("id"), 6);
    omitted.insert(QStringLiteral("clip"), 0);
    omitted.insert(QStringLiteral("start"), 2.0);
    omitted.insert(QStringLiteral("end"), 4.0);
    omitted.insert(QStringLiteral("text"), QStringLiteral("kept without a flag"));
    QVariantMap airDropped;
    airDropped.insert(QStringLiteral("id"), 7);
    airDropped.insert(QStringLiteral("keep"), false);
    airDropped.insert(QStringLiteral("clip"), 0);
    airDropped.insert(QStringLiteral("start"), 40.0);
    airDropped.insert(QStringLiteral("end"), 42.0);
    airDropped.insert(QStringLiteral("text"), QStringLiteral("one span of a wider hole"));
    QVariantMap tailDropped;
    tailDropped.insert(QStringLiteral("id"), 8);
    tailDropped.insert(QStringLiteral("keep"), false);
    tailDropped.insert(QStringLiteral("clip"), 0);
    tailDropped.insert(QStringLiteral("start"), 54.0);
    tailDropped.insert(QStringLiteral("end"), 58.0);
    tailDropped.insert(QStringLiteral("text"), QStringLiteral("dropped tail"));
    backend.setSelects({endsOnHole, dropped, boundary, otherFile, mixedDropped, omitted, airDropped,
                        tailDropped});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->requestActivate();
    window->resize(960, 640);
    QTest::qWait(50);
    QQuickItem *editBar = harness.editBar();
    QVERIFY(editBar);
    QTRY_VERIFY_WITH_TIMEOUT(editBar->isVisible() && editBar->width() > 100, 3000);
    QCOMPARE(editBar->property("plan").toBool(), true);

    QTRY_VERIFY_WITH_TIMEOUT(visibleGap(editBar, 1) && visibleGap(editBar, 2) && visibleGap(editBar, 3)
                                 && visibleGap(editBar, 4),
                             3000);
    QQuickItem *droppedGap = visibleGap(editBar, 1);
    QQuickItem *mixedGap = visibleGap(editBar, 2);
    QQuickItem *airGap = visibleGap(editBar, 3);
    QQuickItem *tailGap = visibleGap(editBar, 4);
    QVERIFY(droppedGap);
    QVERIFY(mixedGap);
    QVERIFY(airGap);
    QVERIFY(tailGap);
    QVERIFY(qAbs(droppedGap->width() - mixedGap->width()) <= 2.0);
    QVERIFY(qAbs(droppedGap->width() - airGap->width()) <= 2.0);
    QVERIFY(qAbs(droppedGap->width() - tailGap->width()) <= 2.0);
    const QColor accent = editBar->property("accent").value<QColor>();
    QVERIFY(accent.isValid());
    const auto rgbSame = [](const QColor &got, const QColor &expected) {
        return qAbs(got.red() - expected.red()) <= 1 && qAbs(got.green() - expected.green()) <= 1
               && qAbs(got.blue() - expected.blue()) <= 1;
    };
    const auto blackAt = [](QQuickItem *gap, int alpha) {
        const QColor color = gap->property("color").value<QColor>();
        return color.red() == 0 && color.green() == 0 && color.blue() == 0
               && qAbs(color.alpha() - alpha) <= 2 && qAbs(gap->opacity() - 1.0) < 0.01;
    };
    QColor droppedColor = droppedGap->property("color").value<QColor>();
    QColor tailColor = tailGap->property("color").value<QColor>();
    QVERIFY2(rgbSame(droppedColor, accent), qPrintable(droppedColor.name(QColor::HexArgb)));
    QCOMPARE(droppedColor.alpha(), 255);
    QVERIFY(qAbs(droppedGap->opacity() - 0.24) < 0.01);
    QVERIFY2(rgbSame(tailColor, accent), qPrintable(tailColor.name(QColor::HexArgb)));
    QCOMPARE(tailColor.alpha(), 255);
    QVERIFY(qAbs(tailGap->opacity() - 0.24) < 0.01);
    QVERIFY2(blackAt(mixedGap, 200), qPrintable(mixedGap->property("color").value<QColor>().name(QColor::HexArgb)));
    QVERIFY2(blackAt(airGap, 200), qPrintable(airGap->property("color").value<QColor>().name(QColor::HexArgb)));
    QVERIFY(qAbs(droppedGap->parentItem()->opacity() - 1.0) < 0.01);
    QVERIFY(qAbs(editBar->opacity() - 1.0) < 0.01);

    // Offscreen delivery of hover is unreliable. gapHovered is what the binding reads.
    QQuickItem *hover = gapHoverArea(editBar);
    QVERIFY(hover);
    QVERIFY(hover->setProperty("gapHovered", 1));
    QTRY_VERIFY_WITH_TIMEOUT(qAbs(droppedGap->opacity() - 0.38) < 0.01, 3000);
    QVERIFY(qAbs(tailGap->opacity() - 0.24) < 0.01);
    QVERIFY2(blackAt(mixedGap, 200), qPrintable(mixedGap->property("color").value<QColor>().name(QColor::HexArgb)));
    QVERIFY2(blackAt(airGap, 200), qPrintable(airGap->property("color").value<QColor>().name(QColor::HexArgb)));
    QVERIFY(hover->setProperty("gapHovered", 2));
    QTRY_VERIFY_WITH_TIMEOUT(qAbs(droppedGap->opacity() - 0.24) < 0.01, 3000);
    QVERIFY2(blackAt(mixedGap, 144), qPrintable(mixedGap->property("color").value<QColor>().name(QColor::HexArgb)));
    QVERIFY2(blackAt(airGap, 200), qPrintable(airGap->property("color").value<QColor>().name(QColor::HexArgb)));
    droppedColor = droppedGap->property("color").value<QColor>();
    QVERIFY(rgbSame(droppedColor, accent));

    backend.setBusy(true);
    QTest::qWait(30);
    QVERIFY(!editBar->isEnabled());
    QVERIFY(qAbs(editBar->opacity() - 0.45) < 0.01);
    QVERIFY(hover->setProperty("gapHovered", 1));
    QTest::qWait(30);
    QVERIFY(qAbs(droppedGap->opacity() - 0.24) < 0.01);
    QVERIFY(qAbs(droppedGap->parentItem()->opacity() - 1.0) < 0.01);
    backend.setBusy(false);
    QTest::qWait(30);
    QVERIFY(qAbs(droppedGap->opacity() - 0.38) < 0.01);

    // The wash follows the line, not the hole's index. A fixed gap index fails one of these.
    QVERIFY(hover->setProperty("gapHovered", -1));
    omitted.insert(QStringLiteral("keep"), false);
    dropped.insert(QStringLiteral("keep"), true);
    backend.setSelects({endsOnHole, dropped, boundary, otherFile, mixedDropped, omitted, airDropped,
                        tailDropped});
    QTRY_VERIFY_WITH_TIMEOUT(qAbs(droppedGap->opacity() - 1.0) < 0.01, 3000);
    droppedColor = droppedGap->property("color").value<QColor>();
    QColor mixedColor = mixedGap->property("color").value<QColor>();
    QCOMPARE(droppedColor.red(), 0);
    QVERIFY(qAbs(droppedColor.alpha() - 200) <= 2);
    QVERIFY(qAbs(droppedGap->opacity() - 1.0) < 0.01);
    QVERIFY2(rgbSame(mixedColor, accent), qPrintable(mixedColor.name(QColor::HexArgb)));
    QCOMPARE(mixedColor.alpha(), 255);
    QVERIFY(qAbs(mixedGap->opacity() - 0.24) < 0.01);
    QVERIFY2(blackAt(airGap, 200), qPrintable(airGap->property("color").value<QColor>().name(QColor::HexArgb)));
    tailColor = tailGap->property("color").value<QColor>();
    QVERIFY2(rgbSame(tailColor, accent), qPrintable(tailColor.name(QColor::HexArgb)));
    QVERIFY(qAbs(tailGap->opacity() - 0.24) < 0.01);

    // A kept line on the tail clears the wash even though the dropped line is still there.
    QVariantMap tailKept;
    tailKept.insert(QStringLiteral("id"), 9);
    tailKept.insert(QStringLiteral("clip"), 0);
    tailKept.insert(QStringLiteral("start"), 54.0);
    tailKept.insert(QStringLiteral("end"), 58.0);
    tailKept.insert(QStringLiteral("text"), QStringLiteral("kept on the tail"));
    backend.setSelects({endsOnHole, dropped, boundary, otherFile, mixedDropped, omitted, airDropped,
                        tailDropped, tailKept});
    QTRY_VERIFY_WITH_TIMEOUT(qAbs(tailGap->opacity() - 1.0) < 0.01, 3000);
    tailColor = tailGap->property("color").value<QColor>();
    QCOMPARE(tailColor.red(), 0);
    QVERIFY(qAbs(tailColor.alpha() - 200) <= 2);
    QVERIFY(qAbs(mixedGap->opacity() - 0.24) < 0.01);
    mixedColor = mixedGap->property("color").value<QColor>();
    QVERIFY2(rgbSame(mixedColor, accent), qPrintable(mixedColor.name(QColor::HexArgb)));

    {
        ShortcutBackend plain(QUrl::fromLocalFile(QStringLiteral("/tmp/plain.mp4")), 20.0);
        QVERIFY(!plain.planCut());
        plain.timeline.split(5.0);
        plain.timeline.split(12.0);
        plain.timeline.removeClip(1);
        QVariantMap line;
        line.insert(QStringLiteral("id"), 1);
        line.insert(QStringLiteral("keep"), false);
        line.insert(QStringLiteral("clip"), 0);
        line.insert(QStringLiteral("start"), 5.0);
        line.insert(QStringLiteral("end"), 12.0);
        line.insert(QStringLiteral("text"), QStringLiteral("dropped on a plain file"));
        plain.setSelects({line});
        QmlHarness plainHarness(plain);
        QQuickWindow *plainWindow = plainHarness.window();
        QVERIFY(plainWindow);
        plainWindow->show();
        plainWindow->requestActivate();
        plainWindow->resize(960, 640);
        QTest::qWait(50);
        QQuickItem *plainBar = plainHarness.editBar();
        QVERIFY(plainBar);
        QTRY_VERIFY_WITH_TIMEOUT(plainBar->isVisible() && plainBar->width() > 100, 3000);
        QCOMPARE(plainBar->property("plan").toBool(), false);
        QQuickItem *plainGap = nullptr;
        QTRY_VERIFY_WITH_TIMEOUT((plainGap = visibleGap(plainBar, 1)) != nullptr, 3000);
        const QColor plainColor = plainGap->property("color").value<QColor>();
        QCOMPARE(plainColor.red(), 0);
        QCOMPARE(plainColor.green(), 0);
        QCOMPARE(plainColor.blue(), 0);
        QVERIFY(qAbs(plainColor.alpha() - 200) <= 2);
        QVERIFY(qAbs(plainGap->opacity() - 1.0) < 0.01);
        const QColor plainAccent = plainBar->property("accent").value<QColor>();
        QVERIFY(!rgbSame(plainColor, plainAccent));

        plain.timeline.reset(20.0);
        QTRY_COMPARE_WITH_TIMEOUT(plain.timeline.clips().size(), 1, 3000);
        QCOMPARE(plain.timeline.clips().at(0).end, 20.0);
        QTRY_VERIFY_WITH_TIMEOUT(plainBar->width() > 100, 3000);
        const QPoint handle = plainBar->mapToScene(QPointF(plainBar->width() - 8, plainBar->height() / 2)).toPoint();
        const QPoint pulled = plainBar->mapToScene(QPointF(plainBar->width() * 0.5, plainBar->height() / 2)).toPoint();
        QTest::mousePress(plainWindow, Qt::LeftButton, Qt::NoModifier, handle);
        QTest::mouseMove(plainWindow, handle + QPoint(-40, 0));
        QTest::mouseMove(plainWindow, pulled);
        QTest::mouseRelease(plainWindow, Qt::LeftButton, Qt::NoModifier, pulled);
        QTRY_VERIFY_WITH_TIMEOUT(plain.timeline.clips().size() == 1
                                     && plain.timeline.clips().at(0).end < 19.0,
                                 3000);
    }
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
                                             QStringLiteral("dip"), QStringLiteral("--max-pause"),
                                             QStringLiteral("0.8"), QStringLiteral("--b-roll-sound"),
                                             QStringLiteral("mix")}));
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

    const CutLaunch hard = cutRunLaunch(files, QStringLiteral("assemble"), QStringLiteral("/tmp/out"),
                                         QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(),
                                         QString(), false, QStringLiteral("off"));
    QCOMPARE(hard.arguments.at(hard.arguments.indexOf(QStringLiteral("--scene-transition")) + 1),
             QStringLiteral("off"));
    QVERIFY(!hard.arguments.contains(QStringLiteral("--decide")));
    QCOMPARE(hard.arguments.at(hard.arguments.indexOf(QStringLiteral("--max-pause")) + 1),
             QStringLiteral("0.8"));

    const CutLaunch frenzied = cutRunLaunch(files, QStringLiteral("speech"), QStringLiteral("/tmp/out"),
                                             QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(),
                                             QString(), false, QStringLiteral("dip"), 0.1);
    QCOMPARE(frenzied.arguments.at(frenzied.arguments.indexOf(QStringLiteral("--max-pause")) + 1),
             QStringLiteral("0.1"));
    QVERIFY(!frenzied.arguments.contains(QStringLiteral("--b-roll-file")));

    const CutLaunch covered = cutRunLaunch(files, QStringLiteral("speech"), QStringLiteral("/tmp/out"),
                                            QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(),
                                            QString(), true, QStringLiteral("dip"), 0.8,
                                            {QStringLiteral("/tmp/b.mp4"), QStringLiteral("/tmp/zz.mp4")});
    const int coveredPause = covered.arguments.indexOf(QStringLiteral("--max-pause"));
    QCOMPARE(covered.arguments.at(coveredPause + 2), QStringLiteral("--b-roll-file"));
    QCOMPARE(covered.arguments.at(coveredPause + 3), QStringLiteral("/tmp/b.mp4"));
    // A B-roll path that is not one of the files is not sent.
    QCOMPARE(covered.arguments.count(QStringLiteral("--b-roll-file")), 1);
    QVERIFY(!covered.arguments.contains(QStringLiteral("/tmp/zz.mp4")));
    QCOMPARE(covered.arguments.at(coveredPause + 4), QStringLiteral("--b-roll-sound"));
    QCOMPARE(covered.arguments.at(coveredPause + 5), QStringLiteral("mix"));
    QCOMPARE(covered.arguments.last(), QStringLiteral("--decide"));
    QVERIFY(!covered.arguments.contains(QStringLiteral("--b-roll")));

    // Assemble plays every file, so the mark stays home.
    const CutLaunch assembled = cutRunLaunch(files, QStringLiteral("assemble"), QStringLiteral("/tmp/out"),
                                              QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(),
                                              QString(), false, QStringLiteral("dip"), 0.8,
                                              {QStringLiteral("/tmp/b.mp4")});
    QVERIFY(!assembled.arguments.contains(QStringLiteral("--b-roll-file")));
    QCOMPARE(assembled.arguments.count(QStringLiteral("/tmp/b.mp4")), 1);

    const CutLaunch voiceSound = cutRunLaunch(files, QStringLiteral("speech"), QStringLiteral("/tmp/out"),
                                               QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(),
                                               QString(), false, QStringLiteral("dip"), 0.8, {}, false);
    QCOMPARE(voiceSound.arguments.at(voiceSound.arguments.indexOf(QStringLiteral("--b-roll-sound")) + 1),
             QStringLiteral("voice"));
    QVERIFY(!voiceSound.arguments.contains(QStringLiteral("--b-roll-file")));
    QVERIFY(!voiceSound.arguments.contains(QStringLiteral("clip")));

    const CutLaunch rendered = cutRenderLaunch(QStringLiteral("/tmp/out"),
                                                QStringLiteral("/usr/bin/botcut-cli"), QString(),
                                                QString(), QStringLiteral("weird"));
    QCOMPARE(rendered.arguments, (QStringList{QStringLiteral("render"), QStringLiteral("/tmp/out"),
                                               QStringLiteral("--scene-transition"),
                                               QStringLiteral("dip"), QStringLiteral("--b-roll-sound"),
                                               QStringLiteral("mix")}));
    const CutLaunch renderedVoice = cutRenderLaunch(QStringLiteral("/tmp/out"),
                                                     QStringLiteral("/usr/bin/botcut-cli"), QString(),
                                                     QString(), QStringLiteral("dip"), false);
    QCOMPARE(renderedVoice.arguments.last(), QStringLiteral("voice"));

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
    QCOMPARE(first.brollMix(), true);
    QCOMPARE(first.pace(), QStringLiteral("open"));
    QCOMPARE(first.maxPause(), 0.8);
    first.setSceneTransition(QStringLiteral("off"));
    QCOMPARE(first.sceneTransition(), QStringLiteral("off"));
    first.setBrollMix(false);
    QCOMPARE(first.brollMix(), false);
    first.setPace(QStringLiteral("frenzied"));
    QCOMPARE(first.pace(), QStringLiteral("frenzied"));
    QCOMPARE(first.maxPause(), 0.1);
    first.setPace(QStringLiteral("tight"));
    QCOMPARE(first.maxPause(), 0.28);
    first.setPace(QStringLiteral("measured"));
    QCOMPARE(first.maxPause(), 0.4);

    auto *againPicker = new FakeFilePicker;
    Backend again(&provider, againPicker);
    QCOMPARE(again.sceneTransition(), QStringLiteral("off"));
    QCOMPARE(again.brollMix(), false);
    QCOMPARE(again.pace(), QStringLiteral("measured"));
    QCOMPARE(again.maxPause(), 0.4);
    again.setSceneTransition(QStringLiteral("nope"));
    QCOMPARE(again.sceneTransition(), QStringLiteral("dip"));
    again.setBrollMix(true);
    QCOMPARE(again.brollMix(), true);
    again.setPace(QStringLiteral("nope"));
    QCOMPARE(again.pace(), QStringLiteral("open"));
    QCOMPARE(again.maxPause(), 0.8);

    auto *thirdPicker = new FakeFilePicker;
    Backend third(&provider, thirdPicker);
    QCOMPARE(third.sceneTransition(), QStringLiteral("dip"));
    QCOMPARE(third.brollMix(), true);
    QCOMPARE(third.pace(), QStringLiteral("open"));
    third.setSceneTransition(QStringLiteral("dip"));
    QCOMPARE(third.sceneTransition(), QStringLiteral("dip"));
    third.setPace(QStringLiteral("open"));
    QCOMPARE(third.pace(), QStringLiteral("open"));
    // An old "broll" switch left in settings means nothing now.
    QSettings().setValue(QStringLiteral("broll"), true);
    QSettings().setValue(QStringLiteral("brollMix"), QStringLiteral("false"));
    Backend exactFalse(&provider, new FakeFilePicker);
    QCOMPARE(exactFalse.brollMix(), false);
    QSettings().setValue(QStringLiteral("brollMix"), QStringLiteral("False"));
    Backend capitalFalse(&provider, new FakeFilePicker);
    QCOMPARE(capitalFalse.brollMix(), true);
    QSettings().setValue(QStringLiteral("brollMix"), QStringLiteral("0"));
    Backend zero(&provider, new FakeFilePicker);
    QCOMPARE(zero.brollMix(), true);
    // A default-constructed QString is a null variant, and setValue drops the key.
    QSettings().setValue(QStringLiteral("brollMix"), QStringLiteral(""));
    QVERIFY(QSettings().contains(QStringLiteral("brollMix")));
    Backend empty(&provider, new FakeFilePicker);
    QCOMPARE(empty.brollMix(), true);
    QSettings().remove(QStringLiteral("brollMix"));
    Backend absent(&provider, new FakeFilePicker);
    QCOMPARE(absent.brollMix(), true);
}

void BackendTests::clearCoverKeepsTheWords() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString dir = m_dir.filePath(QStringLiteral("cover-clear"));
    QVERIFY(QDir().mkpath(dir));
    backend.m_cutOut = dir;

    QVariantMap line;
    line.insert(QStringLiteral("id"), 4);
    line.insert(QStringLiteral("clip"), 0);
    line.insert(QStringLiteral("start"), 1.0);
    line.insert(QStringLiteral("end"), 3.0);
    line.insert(QStringLiteral("text"), QStringLiteral("hello there"));
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("reason"), QStringLiteral("story"));
    QVariantMap other = line;
    other.insert(QStringLiteral("id"), 5);
    other.insert(QStringLiteral("text"), QStringLiteral("the next line"));
    backend.m_selects = {line, other};
    QVariantMap cover;
    cover.insert(QStringLiteral("clip"), 2);
    cover.insert(QStringLiteral("line"), 4);
    QVariantMap otherCover;
    otherCover.insert(QStringLiteral("clip"), 3);
    otherCover.insert(QStringLiteral("line"), 5);
    backend.m_covers = {cover, otherCover};

    const QString cuts = QDir(dir).filePath(QStringLiteral("cuts.json"));
    QJsonArray lines;
    QJsonObject kept;
    kept.insert(QStringLiteral("id"), 4);
    kept.insert(QStringLiteral("clip"), 0);
    kept.insert(QStringLiteral("start"), 1.0);
    kept.insert(QStringLiteral("end"), 3.0);
    kept.insert(QStringLiteral("text"), QStringLiteral("hello there"));
    kept.insert(QStringLiteral("keep"), true);
    kept.insert(QStringLiteral("reason"), QStringLiteral("story"));
    QJsonObject next = kept;
    next.insert(QStringLiteral("id"), 5);
    next.insert(QStringLiteral("text"), QStringLiteral("the next line"));
    lines.append(kept);
    lines.append(next);
    QJsonArray rows;
    QJsonObject item;
    item.insert(QStringLiteral("clip"), 2);
    item.insert(QStringLiteral("line"), 4);
    QJsonObject itemNext;
    itemNext.insert(QStringLiteral("clip"), 3);
    itemNext.insert(QStringLiteral("line"), 5);
    rows.append(item);
    rows.append(itemNext);
    QJsonObject segment;
    segment.insert(QStringLiteral("clip"), 0);
    segment.insert(QStringLiteral("start"), 1.0);
    segment.insert(QStringLiteral("end"), 8.0);
    QJsonObject tighten;
    tighten.insert(QStringLiteral("max_pause"), 0.4);
    QJsonObject root;
    root.insert(QStringLiteral("lines"), lines);
    root.insert(QStringLiteral("covers"), rows);
    root.insert(QStringLiteral("segments"), QJsonArray{segment});
    root.insert(QStringLiteral("trimmed"), true);
    root.insert(QStringLiteral("tighten"), tighten);
    const auto writeRoot = [&cuts](const QJsonObject &object) {
        QFile file(cuts);
        if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
            return false;
        const QByteArray bytes = QJsonDocument(object).toJson(QJsonDocument::Indented);
        return file.write(bytes) == bytes.size();
    };
    const auto readRoot = [&cuts]() {
        QFile file(cuts);
        if (!file.open(QIODevice::ReadOnly))
            return QJsonObject();
        return QJsonDocument::fromJson(file.readAll()).object();
    };
    QVERIFY(writeRoot(root));

    backend.clearCover(99);
    QCOMPARE(backend.covers().size(), 2);
    QCOMPARE(readRoot().value(QStringLiteral("covers")).toArray().size(), 2);

    backend.clearCover(4);
    QCOMPARE(backend.covers().size(), 1);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("line")).toInt(), 5);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello there"));
    const QJsonObject afterClear = readRoot();
    const QJsonArray clearedLines = afterClear.value(QStringLiteral("lines")).toArray();
    QCOMPARE(clearedLines.at(0).toObject().value(QStringLiteral("keep")).toBool(), true);
    QCOMPARE(clearedLines.at(0).toObject().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello there"));
    const QJsonArray clearedCovers = afterClear.value(QStringLiteral("covers")).toArray();
    QCOMPARE(clearedCovers.size(), 1);
    QCOMPARE(clearedCovers.at(0).toObject().value(QStringLiteral("clip")).toInt(), 3);
    QCOMPARE(clearedCovers.at(0).toObject().value(QStringLiteral("line")).toInt(), 5);
    QCOMPARE(afterClear.value(QStringLiteral("segments")).toArray().at(0).toObject().value(QStringLiteral("end")).toDouble(),
             8.0);
    QCOMPARE(afterClear.value(QStringLiteral("trimmed")).toBool(), true);
    QCOMPARE(afterClear.value(QStringLiteral("tighten")).toObject().value(QStringLiteral("max_pause")).toDouble(), 0.4);

    QVERIFY(writeRoot(root));
    backend.m_covers = {cover, otherCover};
    backend.m_selects = {line, other};
    backend.dropSelect(4);
    QVERIFY(!backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello there"));
    QCOMPARE(backend.covers().size(), 1);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("line")).toInt(), 5);
    const QJsonObject afterDrop = readRoot();
    const QJsonArray droppedLines = afterDrop.value(QStringLiteral("lines")).toArray();
    QCOMPARE(droppedLines.at(0).toObject().value(QStringLiteral("keep")).toBool(), false);
    QCOMPARE(droppedLines.at(0).toObject().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello there"));
    QCOMPARE(droppedLines.at(1).toObject().value(QStringLiteral("keep")).toBool(), true);
    const QJsonArray droppedCovers = afterDrop.value(QStringLiteral("covers")).toArray();
    QCOMPARE(droppedCovers.size(), 1);
    QCOMPARE(droppedCovers.at(0).toObject().value(QStringLiteral("line")).toInt(), 5);
    QCOMPARE(afterDrop.value(QStringLiteral("segments")).toArray().at(0).toObject().value(QStringLiteral("end")).toDouble(),
             8.0);
    QCOMPARE(afterDrop.value(QStringLiteral("trimmed")).toBool(), true);
    QCOMPARE(afterDrop.value(QStringLiteral("tighten")).toObject().value(QStringLiteral("max_pause")).toDouble(), 0.4);

    QVERIFY(QFile::setPermissions(dir, QFileDevice::ReadOwner | QFileDevice::ExeOwner));
    backend.clearCover(5);
    QCOMPARE(backend.status(), QStringLiteral("Could not save the line list"));
    QCOMPARE(backend.covers().size(), 1);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("line")).toInt(), 5);
    backend.m_selects[1] = other;
    backend.dropSelect(5);
    QCOMPARE(backend.status(), QStringLiteral("Could not save the line list"));
    QVERIFY(backend.selects().at(1).toMap().value(QStringLiteral("keep")).toBool());
    QCOMPARE(backend.covers().size(), 1);
    QVERIFY(QFile::setPermissions(dir, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));
    const QJsonObject stillThere = readRoot();
    QCOMPARE(stillThere.value(QStringLiteral("covers")).toArray().at(0).toObject().value(QStringLiteral("line")).toInt(),
             5);
    QCOMPARE(stillThere.value(QStringLiteral("lines")).toArray().at(1).toObject().value(QStringLiteral("keep")).toBool(),
             true);
}

void BackendTests::coverHoverNamesTheCutClip() {
    ShortcutBackend backend(QUrl(), 0.0);
    QVariantMap first;
    first.insert(QStringLiteral("id"), 4);
    first.insert(QStringLiteral("text"), QStringLiteral("the spoken line"));
    first.insert(QStringLiteral("keep"), true);
    first.insert(QStringLiteral("reason"), QStringLiteral("story"));
    QVariantMap second;
    second.insert(QStringLiteral("id"), 5);
    second.insert(QStringLiteral("text"), QStringLiteral("the other line"));
    second.insert(QStringLiteral("keep"), true);
    second.insert(QStringLiteral("reason"), QStringLiteral("story"));
    backend.setSelects({first, second});
    backend.setTray({QStringLiteral("/tmp/not-the-cut-a.mp4"), QStringLiteral("/tmp/not-the-cut-b.mp4")});
    QVariantMap coverA;
    coverA.insert(QStringLiteral("clip"), 1);
    coverA.insert(QStringLiteral("line"), 4);
    QVariantMap coverB;
    coverB.insert(QStringLiteral("clip"), 0);
    coverB.insert(QStringLiteral("line"), 5);
    backend.setCovers({coverA, coverB});
    backend.setCutClips({QStringLiteral("/cuts/speaker.mp4"), QStringLiteral("/cuts/room.mp4")});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(50);
    QCOMPARE(window->property("currentLine").toInt(), 0);
    QVERIFY(visibleItemWithText(window, QStringLiteral("B-roll: room.mp4")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("B-roll: speaker.mp4")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("room.mp4")));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Clear")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("the spoken line")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("the other line")));
    QQuickItem *remove = visibleItemWithText(window, QStringLiteral("Remove B-roll"));
    QVERIFY(remove);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(remove));
    QTest::qWait(50);
    QVERIFY(!visibleItemWithText(window, QStringLiteral("B-roll: room.mp4")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("B-roll: speaker.mp4")));
    QCOMPARE(backend.covers().size(), 1);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("line")).toInt(), 5);
    window->setProperty("currentLine", 1);
    QTest::qWait(50);
    QVERIFY(visibleItemWithText(window, QStringLiteral("B-roll: speaker.mp4")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("Remove B-roll")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("the spoken line")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("the other line")));
}

void BackendTests::loadSelectsKeepsClipArrayOrder() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString dir = m_dir.filePath(QStringLiteral("clip-order"));
    QVERIFY(QDir().mkpath(dir));
    const QString cuts = QDir(dir).filePath(QStringLiteral("cuts.json"));
    const QString room = QStringLiteral("/cuts/room.mp4");
    const QString speaker = QStringLiteral("/cuts/speaker.mp4");
    // Indexes 2 then 0 skip 1. Cover numbers follow the array, not a sort that inserts a blank.
    QJsonObject first;
    first.insert(QStringLiteral("index"), 2);
    first.insert(QStringLiteral("path"), room);
    QJsonObject second;
    second.insert(QStringLiteral("index"), 0);
    second.insert(QStringLiteral("path"), speaker);
    QJsonArray clips;
    clips.append(first);
    clips.append(second);
    QJsonObject cover0;
    cover0.insert(QStringLiteral("clip"), 0);
    cover0.insert(QStringLiteral("line"), 4);
    QJsonObject cover1;
    cover1.insert(QStringLiteral("clip"), 1);
    cover1.insert(QStringLiteral("line"), 5);
    QJsonArray covers;
    covers.append(cover0);
    covers.append(cover1);
    QJsonObject root;
    root.insert(QStringLiteral("clips"), clips);
    root.insert(QStringLiteral("covers"), covers);
    QFile file(cuts);
    QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Indented);
    QCOMPARE(file.write(bytes), bytes.size());
    file.close();

    backend.loadSelects(cuts);
    const QStringList paths = backend.cutClips();
    QCOMPARE(paths, QStringList({room, speaker}));
    QVERIFY(!paths.contains(QString()));
    QCOMPARE(backend.covers().size(), 2);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("clip")).toInt(), 0);
    QCOMPARE(paths.at(0), room);
    QCOMPARE(backend.covers().at(1).toMap().value(QStringLiteral("clip")).toInt(), 1);
    QCOMPARE(paths.at(1), speaker);
}

void BackendTests::assembleLaunchOmitsBroll() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString clip = m_dir.filePath(QStringLiteral("assemble-broll.mp4"));
    const QString room = m_dir.filePath(QStringLiteral("assemble-room.mp4"));
    QVERIFY(QFile(clip).open(QIODevice::WriteOnly));
    QVERIFY(QFile(room).open(QIODevice::WriteOnly));
    const QString roomPath = QFileInfo(room).absoluteFilePath();
    backend.m_tray = {QFileInfo(clip).absoluteFilePath(), roomPath};
    backend.m_trayIndex = 0;
    backend.toggleBroll(1);
    QCOMPARE(backend.brollFiles(), QStringList{roomPath});
    backend.m_cutMode = QStringLiteral("assemble");
    backend.m_launchProgram = QStringLiteral("/bin/true");
    backend.startCut();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QVERIFY(backend.m_cutProcess);
    QVERIFY(!backend.m_cutProcess->arguments().contains(QStringLiteral("--b-roll-file")));
    QVERIFY(!backend.m_cutProcess->arguments().contains(QStringLiteral("--b-roll")));

    backend.m_cutMode = QStringLiteral("speech");
    backend.setApiKey(QStringLiteral("not-a-real-key"));
    backend.startCut();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    const QStringList args = backend.m_cutProcess->arguments();
    const int pause = args.indexOf(QStringLiteral("--max-pause"));
    QVERIFY(pause >= 0);
    QCOMPARE(args.at(pause + 2), QStringLiteral("--b-roll-file"));
    QCOMPARE(args.at(pause + 3), roomPath);
    QCOMPARE(args.count(QStringLiteral("--b-roll-file")), 1);
    QCOMPARE(args.at(args.indexOf(QStringLiteral("--b-roll-sound")) + 1), QStringLiteral("mix"));
    QCOMPARE(args.last(), QStringLiteral("--decide"));
    QVERIFY(!args.contains(QStringLiteral("not-a-real-key")));
    backend.setBrollMix(false);
    backend.startCut();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    const QStringList voiceArgs = backend.m_cutProcess->arguments();
    QCOMPARE(voiceArgs.at(voiceArgs.indexOf(QStringLiteral("--b-roll-sound")) + 1), QStringLiteral("voice"));
    QCOMPARE(voiceArgs.at(voiceArgs.indexOf(QStringLiteral("--max-pause")) + 2), QStringLiteral("--b-roll-file"));
    QCOMPARE(voiceArgs.last(), QStringLiteral("--decide"));
    QVERIFY(!voiceArgs.contains(QStringLiteral("not-a-real-key")));
    backend.setBrollMix(true);

    // Unmarking the file takes the flag away again.
    backend.toggleBroll(1);
    QVERIFY(backend.brollFiles().isEmpty());
    backend.startCut();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QVERIFY(!backend.m_cutProcess->arguments().contains(QStringLiteral("--b-roll-file")));
}

void BackendTests::brollRoleRoundTrips() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString talk = QFileInfo(m_dir.filePath(QStringLiteral("role-talk.mp4"))).absoluteFilePath();
    const QString room = QFileInfo(m_dir.filePath(QStringLiteral("role-room.mp4"))).absoluteFilePath();
    const QString card = QFileInfo(m_dir.filePath(QStringLiteral("botcut-card-role-open.mp4"))).absoluteFilePath();
    for (const QString &path : {talk, room, card})
        QVERIFY(QFile(path).open(QIODevice::WriteOnly));
    backend.m_tray = {talk, room, card};
    backend.m_trayIndex = 0;
    QVERIFY(backend.brollFiles().isEmpty());
    QVERIFY(!backend.isBroll(room));

    QSignalSpy tray(&backend, &Backend::trayChanged);
    backend.toggleBroll(1);
    QCOMPARE(tray.count(), 1);
    QVERIFY(backend.isBroll(room));
    QVERIFY(!backend.isBroll(talk));
    QCOMPARE(backend.brollFiles(), QStringList{room});

    // A card, an index off the list, and a busy window change nothing.
    backend.toggleBroll(2);
    backend.toggleBroll(7);
    backend.toggleBroll(-1);
    backend.m_busy = true;
    backend.toggleBroll(0);
    backend.m_busy = false;
    QCOMPARE(backend.brollFiles(), QStringList{room});
    QCOMPARE(tray.count(), 1);

    // The list follows the tray's order, and a move keeps the marks.
    backend.toggleBroll(0);
    QCOMPARE(backend.brollFiles(), (QStringList{talk, room}));
    backend.m_trayIndex = 1;
    backend.moveTray(-1);
    QCOMPARE(backend.tray(), (QStringList{room, talk, card}));
    QCOMPARE(backend.brollFiles(), (QStringList{room, talk}));

    // The saved list carries the marks, and cuts.json carries the role.
    const QString list = m_dir.filePath(QStringLiteral("roles.botcut.json"));
    backend.writeCutListFile(QUrl::fromLocalFile(list));
    QFile listFile(list);
    QVERIFY(listFile.open(QIODevice::ReadOnly));
    const QJsonObject listRoot = QJsonDocument::fromJson(listFile.readAll()).object();
    listFile.close();
    QCOMPARE(listRoot.value(QStringLiteral("broll")).toArray(), (QJsonArray{room, talk}));
    backend.m_cutOut.clear();
    QVERIFY(backend.writeCutsForRender());
    QFile cutsFile(QDir(backend.m_cutOut).filePath(QStringLiteral("cuts.json")));
    QVERIFY(cutsFile.open(QIODevice::ReadOnly));
    const QJsonArray clips = QJsonDocument::fromJson(cutsFile.readAll()).object().value(QStringLiteral("clips")).toArray();
    cutsFile.close();
    QCOMPARE(clips.size(), 3);
    QCOMPARE(clips.at(0).toObject().value(QStringLiteral("role")).toString(), QStringLiteral("broll"));
    QCOMPARE(clips.at(1).toObject().value(QStringLiteral("role")).toString(), QStringLiteral("broll"));
    QVERIFY(!clips.at(2).toObject().contains(QStringLiteral("role")));

    // Removing a file drops its mark. Unmarking by hand does too.
    backend.m_trayIndex = 1;
    backend.removeTray();
    QCOMPARE(backend.tray(), (QStringList{room, card}));
    QCOMPARE(backend.brollFiles(), QStringList{room});
    backend.toggleBroll(0);
    QVERIFY(backend.brollFiles().isEmpty());

    // Reopening the list puts the marks back. Closing the project clears them.
    QVERIFY(backend.loadCutListFile(QUrl::fromLocalFile(list)));
    QCOMPARE(backend.tray(), (QStringList{room, talk, card}));
    QCOMPARE(backend.brollFiles(), (QStringList{room, talk}));
    backend.closeProject();
    QVERIFY(backend.tray().isEmpty());
    QVERIFY(backend.brollFiles().isEmpty());
}

void BackendTests::coversKeepTheBeatWindow() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString dir = m_dir.filePath(QStringLiteral("beat-window"));
    QVERIFY(QDir().mkpath(dir));
    const QString cuts = QDir(dir).filePath(QStringLiteral("cuts.json"));
    const QString json = QStringLiteral(
        "{\"clips\":[{\"index\":0,\"path\":\"/tmp/talk.mp4\",\"duration\":20},"
        "{\"index\":1,\"path\":\"/tmp/room.mp4\",\"duration\":10,\"role\":\"broll\"}],"
        "\"lines\":[{\"id\":4,\"clip\":0,\"start\":1,\"end\":3,\"text\":\"hi\",\"keep\":true,\"reason\":\"story\"},"
        "{\"id\":5,\"clip\":0,\"start\":4,\"end\":6,\"text\":\"there\",\"keep\":true,\"reason\":\"story\"}],"
        "\"segments\":[{\"clip\":0,\"start\":0.75,\"end\":6.4,\"reason\":\"story\"}],"
        "\"covers\":[{\"clip\":1,\"line\":4,\"start\":2.0,\"end\":5.5},{\"clip\":1,\"line\":5}]}");
    QFile file(cuts);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(json.toUtf8());
    file.close();
    backend.m_cutOut = dir;
    backend.loadSelects(cuts);
    QCOMPARE(backend.covers().size(), 2);
    const QVariantMap deep = backend.covers().at(0).toMap();
    QCOMPARE(deep.value(QStringLiteral("clip")).toInt(), 1);
    QCOMPARE(deep.value(QStringLiteral("start")).toDouble(), 2.0);
    QCOMPARE(deep.value(QStringLiteral("end")).toDouble(), 5.5);
    // An older cover has no window and gets none invented.
    const QVariantMap plain = backend.covers().at(1).toMap();
    QVERIFY(!plain.contains(QStringLiteral("start")));
    QVERIFY(!plain.contains(QStringLiteral("end")));

    backend.clearCover(5);
    QCOMPARE(backend.covers().size(), 1);
    QVERIFY(file.open(QIODevice::ReadOnly));
    const QJsonObject root = QJsonDocument::fromJson(file.readAll()).object();
    file.close();
    const QJsonArray saved = root.value(QStringLiteral("covers")).toArray();
    QCOMPARE(saved.size(), 1);
    QCOMPARE(saved.at(0).toObject().value(QStringLiteral("line")).toInt(), 4);
    QCOMPARE(saved.at(0).toObject().value(QStringLiteral("start")).toDouble(), 2.0);
    QCOMPARE(saved.at(0).toObject().value(QStringLiteral("end")).toDouble(), 5.5);
    // The clip row's role is left as it was.
    QCOMPARE(root.value(QStringLiteral("clips")).toArray().at(1).toObject().value(QStringLiteral("role")).toString(),
             QStringLiteral("broll"));
}

void BackendTests::shotRowBrollWord() {
    ShortcutBackend backend(QUrl(), 0.0);
    const QString room = QStringLiteral("/tmp/room.mp4");
    backend.setTray({QStringLiteral("/tmp/shot.mp4"), room, QStringLiteral("/tmp/botcut-card-1-open.mp4")});
    backend.setTrayIndex(1);

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(100);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("shots"));

    // The selected shot offers B-roll beside Remove. No row reads B-roll yet.
    QList<QQuickItem *> words;
    collectVisibleText(window->contentItem(), QStringLiteral("B-roll"), &words);
    QCOMPARE(words.size(), 1);
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Shot")));
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(words.first()));
    QTest::qWait(50);
    QCOMPARE(backend.lastToggleIndex, 1);
    QCOMPARE(backend.brollFiles(), QStringList{room});

    // Now the row's fact reads B-roll, and the word offers Shot.
    words.clear();
    collectVisibleText(window->contentItem(), QStringLiteral("B-roll"), &words);
    QCOMPARE(words.size(), 1);
    QQuickItem *shotWord = visibleItemWithText(window, QStringLiteral("Shot"));
    QVERIFY(shotWord);
    QCOMPARE(shotWord->objectName(), QStringLiteral("brollToggle"));
    QVERIFY(words.first()->objectName() != QStringLiteral("brollToggle"));

    // A card has no toggle. The B-roll fact on the room row stays.
    backend.setTrayIndex(2);
    QTest::qWait(50);
    QVERIFY(!visibleItemWithText(window, QStringLiteral("Shot")));
    words.clear();
    collectVisibleText(window->contentItem(), QStringLiteral("B-roll"), &words);
    QCOMPARE(words.size(), 1);
    QVERIFY(words.first()->objectName() != QStringLiteral("brollToggle"));

    // Busy locks the word without hiding it.
    backend.setTrayIndex(0);
    backend.setBusy(true);
    QTest::qWait(50);
    QQuickItem *toggle = window->findChild<QQuickItem *>(QStringLiteral("brollToggle"));
    if (!toggle)
        toggle = visualItemWithText(window->contentItem(), QStringLiteral("B-roll"), false);
    QVERIFY(toggle);
    words.clear();
    collectVisibleText(window->contentItem(), QStringLiteral("B-roll"), &words);
    QCOMPARE(words.size(), 2);
    for (QQuickItem *item : words) {
        if (item->objectName() == QStringLiteral("brollToggle"))
            QVERIFY(qAbs(item->opacity() - 0.38) < 0.01);
    }
    backend.lastToggleIndex = -1;
    for (QQuickItem *item : words) {
        if (item->objectName() == QStringLiteral("brollToggle"))
            QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(item));
    }
    QCOMPARE(backend.lastToggleIndex, -1);
    backend.setBusy(false);
}

void BackendTests::coverAtWindow() {
    QFile file(QFileInfo(QString::fromUtf8(__FILE__)).dir().absoluteFilePath(
        QStringLiteral("../src/Format.js")));
    QVERIFY(file.open(QIODevice::ReadOnly));
    QString src = QString::fromUtf8(file.readAll());
    src.remove(QStringLiteral(".pragma library"));
    QJSEngine engine;
    const QJSValue loaded = engine.evaluate(src);
    QVERIFY2(!loaded.isError(), qPrintable(loaded.toString()));

    // Three kept lines, 0.5 s apart in one clip, and a run over the second and third.
    const QString setup = QStringLiteral(
        "var lines = [{id: 6, clip: 0, start: 2, end: 4, keep: true},"
        "             {id: 7, clip: 0, start: 10, end: 14, keep: true},"
        "             {id: 8, clip: 0, start: 14.5, end: 18, keep: true},"
        "             {id: 9, clip: 0, start: 20, end: 22, keep: true}];"
        "var covers = [{clip: 1, line: 7, through: 8, start: 30, end: 36, reason: 'the road'}];"
        "var paths = ['/tmp/talk.mp4', '/tmp/room.mp4'];");
    QVERIFY(!engine.evaluate(setup).isError());
    const auto at = [&](const QString &call) { return engine.evaluate(call); };

    // Lines outside the run, and before the run's first line, show nothing.
    QVERIFY(at(QStringLiteral("coverAt(lines, 0, covers, paths, 3, 0.8)")).isNull());
    QVERIFY(at(QStringLiteral("coverAt(lines, 3, covers, paths, 21, 0.8)")).isNull());
    QVERIFY(at(QStringLiteral("coverAt(lines, 1, covers, paths, 9.9, 0.8)")).isNull());
    // Inside the first line: the B-roll file from the run's start.
    QJSValue hit = at(QStringLiteral("coverAt(lines, 1, covers, paths, 11.5, 0.8)"));
    QCOMPARE(hit.property(QStringLiteral("path")).toString(), QStringLiteral("/tmp/room.mp4"));
    QCOMPARE(hit.property(QStringLiteral("src")).toNumber(), 31.5);
    QCOMPARE(hit.property(QStringLiteral("until")).toNumber(), 14.0);
    // On the second line the footage has gone on: the first line's 4 s and its 0.5 s of air.
    hit = at(QStringLiteral("coverAt(lines, 2, covers, paths, 15.0, 0.8)"));
    QCOMPARE(hit.property(QStringLiteral("src")).toNumber(), 35.0);
    // The run is 6 s long, so it ends 1.5 s into the second line.
    QCOMPARE(hit.property(QStringLiteral("until")).toNumber(), 16.0);
    QVERIFY(at(QStringLiteral("coverAt(lines, 2, covers, paths, 16.0, 0.8)")).isNull());
    // A dropped line inside the run breaks it.
    QVERIFY(at(QStringLiteral("coverAt(lines, 2, covers, paths, 15.0, 0.8)")).isObject());
    QVERIFY(!engine.evaluate(QStringLiteral("lines[1].keep = false")).isError());
    QVERIFY(at(QStringLiteral("coverAt(lines, 2, covers, paths, 15.0, 0.8)")).isNull());
    QVERIFY(!engine.evaluate(QStringLiteral("lines[1].keep = true")).isError());
    // An older cover with no run stays on its line for four seconds at most.
    hit = at(QStringLiteral("coverAt(lines, 1, [{clip: 1, line: 7}], paths, 12.0, 0.8)"));
    QCOMPARE(hit.property(QStringLiteral("src")).toNumber(), 2.0);
    QCOMPARE(hit.property(QStringLiteral("until")).toNumber(), 14.0);
    QVERIFY(at(QStringLiteral("coverAt(lines, 1, [{clip: 1, line: 7, start: 0, end: 9}], paths, 13.9, 0.8)")).isObject());
    QVERIFY(at(QStringLiteral("coverAt(lines, 1, [{clip: 1, line: 7, start: 0, end: 9}], paths, 14.0, 0.8)")).isNull());
    QVERIFY(at(QStringLiteral("coverAt(lines, 2, [{clip: 1, line: 7}], paths, 15, 0.8)")).isNull());
    // A clip that is not in the list shows nothing.
    QVERIFY(at(QStringLiteral("coverAt(lines, 1, [{clip: 5, line: 7, through: 8, start: 0, end: 3}], paths, 11)")).isNull());
}

void BackendTests::linesSentenceCountsCovers() {
    ShortcutBackend backend(QUrl(), 0.0);
    const QString talk = QStringLiteral("/tmp/talk.mp4");
    const QString room = QStringLiteral("/tmp/room.mp4");
    backend.setTray({talk, room});
    backend.setCutClips({talk, room});
    QVariantList lines;
    for (int id = 1; id <= 4; ++id) {
        QVariantMap line;
        line.insert(QStringLiteral("id"), id);
        line.insert(QStringLiteral("clip"), 0);
        line.insert(QStringLiteral("start"), id * 10.0);
        line.insert(QStringLiteral("end"), id * 10.0 + 5.0);
        line.insert(QStringLiteral("keep"), id != 4);
        line.insert(QStringLiteral("text"), QStringLiteral("line %1").arg(id));
        lines.append(line);
    }
    backend.setSelects(lines);
    QVariantMap run;
    run.insert(QStringLiteral("clip"), 1);
    run.insert(QStringLiteral("line"), 2);
    run.insert(QStringLiteral("through"), 3);
    run.insert(QStringLiteral("start"), 0.0);
    run.insert(QStringLiteral("end"), 9.6);
    run.insert(QStringLiteral("reason"), QStringLiteral("hides the cut"));
    run.insert(QStringLiteral("still"), QStringLiteral("/tmp/broll-1-0.jpg"));
    QVariantMap onDropped = run;
    onDropped.insert(QStringLiteral("line"), 4);
    onDropped.insert(QStringLiteral("through"), 4);
    backend.setCovers({run, onDropped});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(50);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QQuickItem *sentence = window->findChild<QQuickItem *>(QStringLiteral("actionSentence"));
    QVERIFY(sentence);
    // The run on the dropped line does not count.
    QCOMPARE(sentence->property("text").toString(),
             QStringLiteral("3 of 4 lines kept, 0:15, B-roll over 1 stretch. Render makes the movie."));
    // The first line of the run names the file, the length, and the reason, with the beat's still.
    // The line after it says the B-roll goes on. The first line has no cover words at all.
    QVERIFY(visibleItemWithText(window, QStringLiteral("B-roll: room.mp4 · 10 s · hides the cut")));
    QVERIFY(visibleItemWithText(window, QStringLiteral("B-roll goes on")));
    // Delegates hang off the list's visual tree, not the QObject tree.
    QList<QQuickItem *> stills;
    const std::function<void(QQuickItem *)> walk = [&](QQuickItem *item) {
        if (item->objectName() == QLatin1String("coverStill") && item->isVisible())
            stills.append(item);
        for (QQuickItem *kid : item->childItems())
            walk(kid);
    };
    walk(window->contentItem());
    QCOMPARE(stills.size(), 1);

    // No covers: the sentence is as before. The overlay is off until a frame arrives.
    backend.setCovers({});
    emit backend.infoChanged();
    QTest::qWait(50);
    QCOMPARE(sentence->property("text").toString(),
             QStringLiteral("3 of 4 lines kept, 0:15. Render makes the movie."));
    QVERIFY(!visibleItemWithText(window, QStringLiteral("B-roll goes on")));
    QQuickItem *overlay = window->findChild<QQuickItem *>(QStringLiteral("coverOut"));
    QVERIFY(overlay);
    QVERIFY(!overlay->isVisible());
    QVERIFY(window->property("coverNow").isNull());
}

void BackendTests::clearCoverTakesTheRun() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVariantList lines;
    for (int id = 1; id <= 5; ++id) {
        QVariantMap line;
        line.insert(QStringLiteral("id"), id);
        line.insert(QStringLiteral("keep"), true);
        lines.append(line);
    }
    backend.m_selects = lines;
    QVariantMap run;
    run.insert(QStringLiteral("clip"), 1);
    run.insert(QStringLiteral("line"), 2);
    run.insert(QStringLiteral("through"), 4);
    run.insert(QStringLiteral("start"), 0.0);
    run.insert(QStringLiteral("end"), 7.0);
    QVariantMap old;
    old.insert(QStringLiteral("clip"), 1);
    old.insert(QStringLiteral("line"), 5);
    backend.m_covers = {run, old};
    QCOMPARE(backend.describeCovers(), QStringLiteral("B-roll over 2 stretches, 7 s."));
    // Remove B-roll on a middle line takes the whole run and leaves the older cover alone.
    backend.clearCover(3);
    QCOMPARE(backend.m_covers.size(), 1);
    QCOMPARE(backend.m_covers.first().toMap().value(QStringLiteral("line")).toInt(), 5);
    QCOMPARE(backend.describeCovers(), QStringLiteral("B-roll over 1 stretch, 0 s."));
    // An older cover goes only by its own line.
    backend.clearCover(4);
    QCOMPARE(backend.m_covers.size(), 1);
    backend.clearCover(5);
    QVERIFY(backend.m_covers.isEmpty());
    QCOMPARE(backend.describeCovers(), QString());
}

void BackendTests::changeSentenceNamesTheBroll() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVariantList lines;
    for (int id = 1; id <= 6; ++id) {
        QVariantMap line;
        line.insert(QStringLiteral("id"), id);
        line.insert(QStringLiteral("keep"), true);
        lines.append(line);
    }
    backend.m_selects = lines;
    QVariantMap first;
    first.insert(QStringLiteral("clip"), 1);
    first.insert(QStringLiteral("line"), 2);
    first.insert(QStringLiteral("through"), 3);
    QVariantMap second = first;
    second.insert(QStringLiteral("line"), 5);
    second.insert(QStringLiteral("through"), 5);
    backend.m_covers = {first, second};
    QJsonObject keep;
    QJsonArray kept;
    for (int id = 1; id <= 6; ++id) {
        QJsonObject row;
        row.insert(QStringLiteral("id"), id);
        row.insert(QStringLiteral("reason"), QStringLiteral("story"));
        kept.append(row);
    }
    QJsonObject proposal;
    proposal.insert(QStringLiteral("keep"), kept);
    // No covers in the proposal: nothing is said about B-roll.
    QCOMPARE(backend.describeChange(proposal, false), QString());
    // The same runs, one from another beat: nothing changes.
    QJsonObject sameA;
    sameA.insert(QStringLiteral("beat"), 9);
    sameA.insert(QStringLiteral("line"), 2);
    sameA.insert(QStringLiteral("through"), 3);
    QJsonObject sameB = sameA;
    sameB.insert(QStringLiteral("line"), 5);
    sameB.insert(QStringLiteral("through"), 5);
    proposal.insert(QStringLiteral("covers"), QJsonArray{sameA, sameB});
    QCOMPARE(backend.describeChange(proposal, false), QString());
    // One run goes, one is laid.
    QJsonObject fresh = sameA;
    fresh.insert(QStringLiteral("line"), 4);
    fresh.insert(QStringLiteral("through"), 4);
    proposal.insert(QStringLiteral("covers"), QJsonArray{sameA, fresh});
    QCOMPARE(backend.describeChange(proposal, false),
             QStringLiteral("Lays 1 stretch of B-roll. Drops 1 stretch of B-roll."));
    QCOMPARE(backend.describeChange(proposal, true),
             QStringLiteral("Laid 1 stretch of B-roll. Dropped 1 stretch of B-roll."));
    proposal.insert(QStringLiteral("covers"), QJsonArray{});
    QCOMPARE(backend.describeChange(proposal, false), QStringLiteral("Drops 2 stretches of B-roll."));
}

void BackendTests::cutOpensTheChatWithTheEditorsReply() {
    EnvVarGuard fakeGuard("BOTCUT_FAKE");
    qputenv("BOTCUT_FAKE", "1");
    // The stub stands in for botcut-cli run --decide: it writes a cut with one run and the editor's sentence.
    const QString stub = m_dir.filePath(QStringLiteral("decide-stub.sh"));
    {
        QFile script(stub);
        QVERIFY(script.open(QIODevice::WriteOnly | QIODevice::Truncate));
        const QByteArray body =
            "#!/bin/sh\n"
            "out=\"\"\n"
            "while [ $# -gt 0 ]; do\n"
            "  if [ \"$1\" = \"--out\" ]; then out=\"$2\"; fi\n"
            "  shift\n"
            "done\n"
            "mkdir -p \"$out\"\n"
            "cat > \"$out/cuts.json\" <<'JSON'\n"
            "{\"version\": 1, \"mode\": \"speech\", \"intent\": \"A ride\",\n"
            " \"clips\": [{\"index\": 0, \"path\": \"/tmp/talk.mp4\", \"duration\": 30},\n"
            "           {\"index\": 1, \"path\": \"/tmp/room.mp4\", \"duration\": 20, \"role\": \"broll\"}],\n"
            " \"segments\": [{\"clip\": 0, \"start\": 0.0, \"end\": 20.0, \"reason\": \"story\"}],\n"
            " \"lines\": [{\"id\": 1, \"clip\": 0, \"start\": 1, \"end\": 3, \"text\": \"one\", \"keep\": true, \"reason\": \"story\"},\n"
            "           {\"id\": 2, \"clip\": 0, \"start\": 4, \"end\": 8, \"text\": \"two\", \"keep\": true, \"reason\": \"story\"},\n"
            "           {\"id\": 3, \"clip\": 0, \"start\": 9, \"end\": 12, \"text\": \"three\", \"keep\": true, \"reason\": \"story\"}],\n"
            " \"dropped\": [],\n"
            " \"covers\": [{\"clip\": 1, \"line\": 2, \"through\": 2, \"start\": 0.0, \"end\": 4.0,\n"
            "              \"reason\": \"shows the road\", \"still\": \"work/stills/broll-1-0.jpg\"}],\n"
            " \"covers_reply\": \"I laid the road over the middle line.\"}\n"
            "JSON\n"
            "exit 0\n";
        QVERIFY(script.write(body) > 0);
    }
    QVERIFY(QFile::setPermissions(stub, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString talk = m_dir.filePath(QStringLiteral("decide-talk.mp4"));
    const QString room = m_dir.filePath(QStringLiteral("decide-room.mp4"));
    QVERIFY(QFile(talk).open(QIODevice::WriteOnly));
    QVERIFY(QFile(room).open(QIODevice::WriteOnly));
    backend.m_tray = {talk, room};
    backend.setCutMode(QStringLiteral("speech"));
    backend.setApiKey(QStringLiteral("supersecret"));
    backend.m_launchProgram = stub;
    QVERIFY(backend.chat().isEmpty());

    backend.startCut();
    QVERIFY(backend.busy());
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QCOMPARE(backend.selects().size(), 3);
    QCOMPARE(backend.covers().size(), 1);
    const QVariantMap cover = backend.covers().first().toMap();
    QCOMPARE(cover.value(QStringLiteral("through")).toInt(), 2);
    QCOMPARE(cover.value(QStringLiteral("reason")).toString(), QStringLiteral("shows the road"));
    // The still is resolved beside the cut.
    QCOMPARE(cover.value(QStringLiteral("still")).toString(),
             QDir(backend.m_cutOut).filePath(QStringLiteral("work/stills/broll-1-0.jpg")));
    // The chat opens with the editor's sentence and what it laid. Nothing waits on Apply.
    QCOMPARE(backend.chat().size(), 1);
    const QVariantMap turn = backend.chat().first().toMap();
    QCOMPARE(turn.value(QStringLiteral("role")).toString(), QStringLiteral("bot"));
    QCOMPARE(turn.value(QStringLiteral("text")).toString(), QStringLiteral("I laid the road over the middle line."));
    QCOMPARE(turn.value(QStringLiteral("change")).toString(), QStringLiteral("B-roll over 1 stretch, 4 s."));
    QVERIFY(!backend.proposalPending());
    QVERIFY(!backend.canRevert());
}

void BackendTests::renderSelectsPassesBrollSound() {
    const QString stub = m_dir.filePath(QStringLiteral("render-selects-stub.sh"));
    {
        QFile script(stub);
        QVERIFY(script.open(QIODevice::WriteOnly | QIODevice::Truncate));
        QVERIFY(script.write("#!/bin/sh\nexit 0\n") > 0);
    }
    QVERIFY(QFile::setPermissions(stub, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));

    const QString dir = m_dir.filePath(QStringLiteral("render-selects"));
    QVERIFY(QDir().mkpath(dir));
    const QString cuts = QDir(dir).filePath(QStringLiteral("cuts.json"));
    {
        QFile file(cuts);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        const QByteArray bytes = QJsonDocument(QJsonObject()).toJson(QJsonDocument::Indented);
        QCOMPARE(file.write(bytes), bytes.size());
    }

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    backend.m_selects = {line};
    backend.m_cutOut = dir;
    // The stub stands in for botcut-cli. A real render would encode.
    backend.m_launchProgram = stub;

    backend.renderSelects();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QVERIFY(backend.m_cutProcess);
    QCOMPARE(backend.m_cutProcess->program(), stub);
    const QStringList args = backend.m_cutProcess->arguments();
    QVERIFY(args.contains(QStringLiteral("render")));
    QCOMPARE(args.at(args.indexOf(QStringLiteral("--b-roll-sound")) + 1), QStringLiteral("mix"));

    backend.setBrollMix(false);
    backend.renderSelects();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QCOMPARE(backend.m_cutProcess->program(), stub);
    const QStringList voiceArgs = backend.m_cutProcess->arguments();
    QCOMPARE(voiceArgs.at(voiceArgs.indexOf(QStringLiteral("--b-roll-sound")) + 1), QStringLiteral("voice"));
    backend.setBrollMix(true);
}

void BackendTests::planSegmentWriteLeavesCovers() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString dir = m_dir.filePath(QStringLiteral("plan-covers"));
    QVERIFY(QDir().mkpath(dir));
    const QString movie = QDir(dir).filePath(QStringLiteral("rough_cut.mp4"));
    QFile movieFile(movie);
    QVERIFY(movieFile.open(QIODevice::WriteOnly));
    movieFile.write("not a movie");
    movieFile.close();
    const QString cuts = QDir(dir).filePath(QStringLiteral("cuts.json"));
    QJsonObject clip;
    clip.insert(QStringLiteral("index"), 0);
    clip.insert(QStringLiteral("path"), movie);
    clip.insert(QStringLiteral("duration"), 20);
    QJsonArray clips;
    clips.append(clip);
    QJsonObject seg;
    seg.insert(QStringLiteral("clip"), 0);
    seg.insert(QStringLiteral("start"), 1.0);
    seg.insert(QStringLiteral("end"), 8.0);
    seg.insert(QStringLiteral("reason"), QStringLiteral("fake"));
    QJsonArray segments;
    segments.append(seg);
    QJsonObject cover;
    cover.insert(QStringLiteral("clip"), 2);
    cover.insert(QStringLiteral("line"), 4);
    QJsonArray covers;
    covers.append(cover);
    QJsonObject root;
    root.insert(QStringLiteral("clips"), clips);
    root.insert(QStringLiteral("segments"), segments);
    root.insert(QStringLiteral("covers"), covers);
    QFile file(cuts);
    QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Indented);
    QCOMPARE(file.write(bytes), bytes.size());
    file.close();

    backend.m_path = movie;
    backend.m_planCuts = QFileInfo(cuts).absoluteFilePath();
    backend.m_planMovie = QFileInfo(movie).absoluteFilePath();
    backend.loadPlanFilm();
    QVERIFY(backend.m_plan.active());
    QVERIFY(backend.writePlanSegments());

    QFile writtenFile(cuts);
    QVERIFY(writtenFile.open(QIODevice::ReadOnly));
    QJsonArray written = QJsonDocument::fromJson(writtenFile.readAll()).object().value(QStringLiteral("covers")).toArray();
    writtenFile.close();
    QCOMPARE(written.size(), 1);
    QCOMPARE(written.at(0).toObject().value(QStringLiteral("clip")).toInt(), 2);
    QCOMPARE(written.at(0).toObject().value(QStringLiteral("line")).toInt(), 4);

    backend.m_plan.moveEdge(0, false, 4.0);
    QFile movedFile(cuts);
    QVERIFY(movedFile.open(QIODevice::ReadOnly));
    written = QJsonDocument::fromJson(movedFile.readAll()).object().value(QStringLiteral("covers")).toArray();
    movedFile.close();
    QCOMPARE(written.size(), 1);
    QCOMPARE(written.at(0).toObject().value(QStringLiteral("clip")).toInt(), 2);
    QCOMPARE(written.at(0).toObject().value(QStringLiteral("line")).toInt(), 4);
    QFile trimmed(cuts);
    QVERIFY(trimmed.open(QIODevice::ReadOnly));
    const double end = QJsonDocument::fromJson(trimmed.readAll())
                           .object()
                           .value(QStringLiteral("segments"))
                           .toArray()
                           .at(0)
                           .toObject()
                           .value(QStringLiteral("end"))
                           .toDouble();
    QVERIFY(end < 8.0);
}

void BackendTests::reviseDropsALineAndReverts() {
    EnvVarGuard keyGuard("XAI_API_KEY");
    EnvVarGuard fakeGuard("BOTCUT_FAKE");
    qunsetenv("XAI_API_KEY");
    qputenv("BOTCUT_FAKE", "1");

    const CutLaunch shaped = cutReviseLaunch(
        QStringLiteral("/tmp/out/cuts.json"), QStringLiteral("drop the stumble"),
        QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(), QStringLiteral("measured"),
        QStringLiteral("dip"));
    QCOMPARE(shaped.arguments,
             (QStringList{QStringLiteral("revise"), QStringLiteral("/tmp/out/cuts.json"),
                          QStringLiteral("--pace"), QStringLiteral("measured"),
                          QStringLiteral("--scene-transition"), QStringLiteral("dip"),
                          QStringLiteral("--"), QStringLiteral("drop the stumble")}));
    QVERIFY(!shaped.arguments.contains(QStringLiteral("--max-pause")));
    QVERIFY(!shaped.arguments.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    QVERIFY(!shaped.arguments.contains(QStringLiteral("XAI_API_KEY")));
    const CutLaunch viaUv = cutReviseLaunch(
        QStringLiteral("/tmp/out/cuts.json"), QStringLiteral("drop the stumble"), QString(),
        QStringLiteral("/usr/bin/uv"), QStringLiteral("/home/lonbaker/code/botcut/cli"),
        QStringLiteral("measured"), QStringLiteral("off"));
    QVERIFY(viaUv.arguments.contains(QStringLiteral("revise")));
    QVERIFY(!viaUv.arguments.contains(QStringLiteral("--max-pause")));
    QVERIFY(!viaUv.arguments.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    const CutLaunch blank = cutReviseLaunch(
        QStringLiteral("/tmp/out/cuts.json"), QStringLiteral("  "), QStringLiteral("/usr/bin/botcut-cli"),
        QString(), QString(), QStringLiteral("open"), QStringLiteral("dip"));
    QCOMPARE(blank.error, QStringLiteral("Say what to change"));
    const CutLaunch missingCuts = cutReviseLaunch(QString(), QStringLiteral("note"),
                                                   QStringLiteral("/usr/bin/botcut-cli"), QString(),
                                                   QString(), QStringLiteral("open"), QStringLiteral("dip"));
    QCOMPARE(missingCuts.error, QStringLiteral("No cuts.json"));
    const CutLaunch proposed = cutReviseLaunch(
        QStringLiteral("/tmp/out/cuts.json"), QStringLiteral("drop the stumble"),
        QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(), QStringLiteral("measured"),
        QStringLiteral("dip"), true, QStringLiteral("/tmp/out/chat.json"));
    QCOMPARE(proposed.arguments,
             (QStringList{QStringLiteral("revise"), QStringLiteral("/tmp/out/cuts.json"),
                          QStringLiteral("--pace"), QStringLiteral("measured"),
                          QStringLiteral("--scene-transition"), QStringLiteral("dip"),
                          QStringLiteral("--propose"), QStringLiteral("--history"),
                          QStringLiteral("/tmp/out/chat.json"), QStringLiteral("--"),
                          QStringLiteral("drop the stumble")}));
    const CutLaunch applied = cutApplyLaunch(QStringLiteral("/tmp/out/cuts.json"),
                                             QStringLiteral("/usr/bin/botcut-cli"), QString(), QString());
    QCOMPARE(applied.arguments, (QStringList{QStringLiteral("revise"), QStringLiteral("/tmp/out/cuts.json"),
                                             QStringLiteral("--apply")}));
    QCOMPARE(cutApplyLaunch(QString(), QStringLiteral("/usr/bin/botcut-cli"), QString(), QString()).error,
             QStringLiteral("No cuts.json"));

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.setIntent(QStringLiteral("A quiet ride"));
    backend.setPace(QStringLiteral("measured"));
    backend.setSceneTransition(QStringLiteral("dip"));
    backend.setApiKey(QStringLiteral("supersecret"));
    QVERIFY(!backend.status().contains(QStringLiteral("supersecret")));

    QVariantMap firstLine;
    firstLine.insert(QStringLiteral("id"), 1);
    firstLine.insert(QStringLiteral("clip"), 0);
    firstLine.insert(QStringLiteral("start"), 0.2);
    firstLine.insert(QStringLiteral("end"), 1.2);
    firstLine.insert(QStringLiteral("text"), QStringLiteral("hello there"));
    firstLine.insert(QStringLiteral("keep"), true);
    firstLine.insert(QStringLiteral("reason"), QStringLiteral("story"));
    firstLine.insert(QStringLiteral("still"), QStringLiteral("/tmp/1.jpg"));
    QVariantMap secondLine = firstLine;
    secondLine.insert(QStringLiteral("id"), 2);
    secondLine.insert(QStringLiteral("start"), 2.0);
    secondLine.insert(QStringLiteral("end"), 3.0);
    secondLine.insert(QStringLiteral("text"), QStringLiteral("the stumble"));
    secondLine.insert(QStringLiteral("still"), QStringLiteral("/tmp/2.jpg"));
    QVariantList selects;
    selects.append(firstLine);
    selects.append(secondLine);
    backend.m_selects = selects;

    backend.m_busy = true;
    QVERIFY(!backend.sendRevise(QStringLiteral("drop the stumble")));
    backend.m_busy = false;
    QCOMPARE(backend.chat().size(), 0);
    QVERIFY(!backend.applyProposal());

    const QString out = m_dir.filePath(QStringLiteral("revise-out"));
    QVERIFY(QDir().mkpath(out));
    backend.m_cutOut = out;
    QJsonObject tighten;
    tighten.insert(QStringLiteral("max_pause"), 0.8);
    tighten.insert(QStringLiteral("snap"), true);
    QJsonObject segment;
    segment.insert(QStringLiteral("clip"), 0);
    segment.insert(QStringLiteral("start"), 0.0);
    segment.insert(QStringLiteral("end"), 4.0);
    segment.insert(QStringLiteral("reason"), QStringLiteral("story"));
    QJsonArray segments;
    segments.append(segment);
    QJsonObject clip;
    clip.insert(QStringLiteral("index"), 0);
    clip.insert(QStringLiteral("path"), QStringLiteral("/tmp/a.mp4"));
    clip.insert(QStringLiteral("duration"), 10.0);
    QJsonArray clips;
    clips.append(clip);
    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("mode"), QStringLiteral("speech"));
    root.insert(QStringLiteral("intent"), QStringLiteral("A quiet ride"));
    root.insert(QStringLiteral("tighten"), tighten);
    root.insert(QStringLiteral("clips"), clips);
    root.insert(QStringLiteral("segments"), segments);
    root.insert(QStringLiteral("lines"), QJsonArray());
    root.insert(QStringLiteral("dropped"), QJsonArray());
    QJsonObject cover;
    cover.insert(QStringLiteral("clip"), 3);
    cover.insert(QStringLiteral("line"), 2);
    QJsonArray covers;
    covers.append(cover);
    root.insert(QStringLiteral("covers"), covers);
    QVariantMap coverRow;
    coverRow.insert(QStringLiteral("clip"), 3);
    coverRow.insert(QStringLiteral("line"), 2);
    backend.m_covers = {coverRow};
    const QString cuts = QDir(out).filePath(QStringLiteral("cuts.json"));
    {
        QFile file(cuts);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Indented);
        QCOMPARE(file.write(bytes), bytes.size());
    }

    const auto readRoot = [&cuts]() {
        QFile in(cuts);
        if (!in.open(QIODevice::ReadOnly))
            return QJsonObject();
        return QJsonDocument::fromJson(in.readAll()).object();
    };
    const auto lineById = [](const QVariantList &rows, int id) {
        for (const QVariant &item : rows) {
            const QVariantMap row = item.toMap();
            if (row.value(QStringLiteral("id")).toInt() == id)
                return row;
        }
        return QVariantMap();
    };

    QVERIFY2(backend.sendRevise(QStringLiteral("drop the stumble")), qPrintable(backend.status()));
    QCOMPARE(backend.chat().size(), 1);
    QCOMPARE(backend.chat().at(0).toMap().value(QStringLiteral("role")).toString(), QStringLiteral("you"));
    QCOMPARE(backend.chat().at(0).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("drop the stumble"));
    QVERIFY(backend.m_cutProcess);
    const QStringList reviseArgs = backend.m_cutProcess->arguments();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    // A proposal only. The lines, the pace, and the sentence wait for Apply.
    QVERIFY2(backend.proposalPending(), qPrintable(backend.status()));
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
    QCOMPARE(backend.intent(), QStringLiteral("A quiet ride"));
    QVERIFY(lineById(backend.selects(), 2).value(QStringLiteral("keep")).toBool());
    QVERIFY(!backend.canRevert());
    QCOMPARE(backend.chat().size(), 2);
    const QVariantMap proposal = backend.chat().at(1).toMap();
    QCOMPARE(proposal.value(QStringLiteral("role")).toString(), QStringLiteral("bot"));
    QCOMPARE(proposal.value(QStringLiteral("text")).toString(),
             QStringLiteral("I'd drop the last line and cut every breath."));
    QCOMPARE(proposal.value(QStringLiteral("change")).toString(),
             QStringLiteral("Drops 1 line. New movie sentence. Pace becomes Frenzied. Fade to black off."));
    QVERIFY(QFileInfo::exists(QDir(out).filePath(QStringLiteral("proposal.json"))));
    QVERIFY(QFileInfo::exists(QDir(out).filePath(QStringLiteral("chat.json"))));
    QVERIFY(reviseArgs.contains(QStringLiteral("--propose")));
    QCOMPARE(reviseArgs.at(reviseArgs.indexOf(QStringLiteral("--history")) + 1),
             QDir(out).filePath(QStringLiteral("chat.json")));

    QVERIFY2(backend.applyProposal(), qPrintable(backend.status()));
    QVERIFY(backend.busy());
    const QStringList applyArgs = backend.m_cutProcess->arguments();
    QCOMPARE(applyArgs.last(), QStringLiteral("--apply"));
    QVERIFY(!applyArgs.contains(QStringLiteral("--propose")));
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    QVERIFY(!backend.proposalPending());
    QVERIFY(!QFileInfo::exists(QDir(out).filePath(QStringLiteral("proposal.json"))));
    QVERIFY2(backend.pace() == QLatin1String("frenzied"), qPrintable(backend.status()));
    QCOMPARE(backend.intent(), QStringLiteral("A frenzied cut."));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("off"));
    QCOMPARE(backend.status(), QStringLiteral("Ready to render"));
    QVERIFY(!backend.status().contains(QStringLiteral("supersecret")));
    QCOMPARE(backend.selects().size(), 2);
    const QVariantMap kept = lineById(backend.selects(), 1);
    const QVariantMap dropped = lineById(backend.selects(), 2);
    QVERIFY(!kept.isEmpty());
    QVERIFY(!dropped.isEmpty());
    QVERIFY(kept.value(QStringLiteral("keep")).toBool());
    QCOMPARE(kept.value(QStringLiteral("reason")).toString(), QStringLiteral("fake"));
    QCOMPARE(kept.value(QStringLiteral("start")).toDouble(), 0.2);
    QCOMPARE(kept.value(QStringLiteral("text")).toString(), QStringLiteral("hello there"));
    QCOMPARE(kept.value(QStringLiteral("still")).toString(), QStringLiteral("/tmp/1.jpg"));
    QVERIFY(!dropped.value(QStringLiteral("keep")).toBool());
    QCOMPARE(dropped.value(QStringLiteral("reason")).toString(), QStringLiteral("dropped"));
    QCOMPARE(dropped.value(QStringLiteral("end")).toDouble(), 3.0);
    QCOMPARE(dropped.value(QStringLiteral("text")).toString(), QStringLiteral("the stumble"));
    for (const QVariant &item : backend.selects())
        QVERIFY(item.toMap().value(QStringLiteral("id")).toInt() != 1000000000);
    QVERIFY(backend.canRevert());
    QCOMPARE(backend.chat().size(), 3);
    const QVariantMap done = backend.chat().at(2).toMap();
    QCOMPARE(done.value(QStringLiteral("text")).toString(), QStringLiteral("Done."));
    QCOMPARE(done.value(QStringLiteral("change")).toString(),
             QStringLiteral("Dropped 1 line. New movie sentence. Pace is now Frenzied. Fade to black off."));
    QVERIFY(!QFileInfo::exists(QDir(out).filePath(QStringLiteral("rough_cut.mp4"))));
    QVERIFY(!QFileInfo::exists(QDir(out).filePath(QStringLiteral("short.mp4"))));
    QVERIFY(!QFileInfo::exists(QDir(out).filePath(QStringLiteral("rough_cut.srt"))));

    QVERIFY(reviseArgs.contains(QStringLiteral("revise")));
    QCOMPARE(reviseArgs.at(reviseArgs.lastIndexOf(QStringLiteral("--")) + 1),
             QStringLiteral("drop the stumble"));
    QVERIFY(!reviseArgs.contains(QStringLiteral("--max-pause")));
    QVERIFY(!reviseArgs.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    QVERIFY(!reviseArgs.contains(QStringLiteral("XAI_API_KEY")));
    QCOMPARE(backend.m_cutProcess->processEnvironment().value(QStringLiteral("XAI_API_KEY")),
             QStringLiteral("supersecret"));
    QCOMPARE(backend.m_cutProcess->processEnvironment().value(QStringLiteral("BOTCUT_FAKE")),
             QStringLiteral("1"));

    // The file still has the last Cut's pause. Measured is only the control, and
    // Frenzied is not written until the next Cut or Render.
    const QJsonObject revised = readRoot();
    QCOMPARE(revised.value(QStringLiteral("tighten")).toObject().value(QStringLiteral("max_pause")).toDouble(),
             0.8);
    QCOMPARE(revised.value(QStringLiteral("tighten")).toObject().value(QStringLiteral("snap")).toBool(), true);
    QCOMPARE(revised.value(QStringLiteral("segments")).toArray().at(0).toObject().value(QStringLiteral("end")).toDouble(),
             4.0);
    QCOMPARE(backend.maxPause(), 0.1);
    const CutLaunch nextCut = cutRunLaunch(
        {QStringLiteral("/tmp/a.mp4")}, QStringLiteral("speech"), out, QStringLiteral("/usr/bin/botcut-cli"),
        QString(), QString(), backend.intent(), false, backend.sceneTransition(), backend.maxPause());
    QCOMPARE(nextCut.arguments.at(nextCut.arguments.indexOf(QStringLiteral("--max-pause")) + 1),
             QStringLiteral("0.1"));
    QVERIFY(backend.writeSelects(cuts));
    QCOMPARE(readRoot().value(QStringLiteral("tighten")).toObject().value(QStringLiteral("max_pause")).toDouble(),
             0.1);
    QCOMPARE(backend.covers().size(), 0);
    QVERIFY(!readRoot().contains(QStringLiteral("covers")));

    QVERIFY(QFile::setPermissions(cuts, QFileDevice::ReadOwner));
    backend.revertRevise();
    QVERIFY(backend.canRevert());
    QVERIFY(!lineById(backend.selects(), 2).value(QStringLiteral("keep")).toBool());
    QCOMPARE(backend.covers().size(), 0);
    QCOMPARE(backend.status(), QStringLiteral("Could not save the line list"));
    QVERIFY(QFile::setPermissions(cuts, QFileDevice::ReadOwner | QFileDevice::WriteOwner));

    backend.revertRevise();
    QCOMPARE(backend.intent(), QStringLiteral("A quiet ride"));
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
    QCOMPARE(backend.maxPause(), 0.4);
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));
    QVERIFY(!backend.canRevert());
    QCOMPARE(backend.chat().size(), 3);
    QVERIFY(lineById(backend.selects(), 2).value(QStringLiteral("keep")).toBool());
    QCOMPARE(backend.covers().size(), 1);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("clip")).toInt(), 3);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("line")).toInt(), 2);
    QCOMPARE(readRoot().value(QStringLiteral("covers")).toArray().at(0).toObject().value(QStringLiteral("line")).toInt(),
             2);
    QCOMPARE(lineById(backend.selects(), 2).value(QStringLiteral("reason")).toString(),
             QStringLiteral("story"));
    QCOMPARE(lineById(backend.selects(), 1).value(QStringLiteral("still")).toString(),
             QStringLiteral("/tmp/1.jpg"));
    QCOMPARE(readRoot().value(QStringLiteral("tighten")).toObject().value(QStringLiteral("max_pause")).toDouble(),
             0.1);
    const QJsonArray restoredLines = readRoot().value(QStringLiteral("lines")).toArray();
    QCOMPARE(restoredLines.size(), 2);
    QCOMPARE(restoredLines.at(1).toObject().value(QStringLiteral("keep")).toBool(), true);

    backend.setPace(QStringLiteral("tight"));
    backend.setIntent(QStringLiteral("Hand edit"));
    backend.setSceneTransition(QStringLiteral("off"));
    QVERIFY(backend.sendRevise(QStringLiteral("keep going")));
    const QStringList secondArgs = backend.m_cutProcess->arguments();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    QVERIFY(backend.proposalPending());
    // The earlier turns went along as history.
    {
        QFile history(QDir(out).filePath(QStringLiteral("chat.json")));
        QVERIFY(history.open(QIODevice::ReadOnly));
        const QJsonArray turns = QJsonDocument::fromJson(history.readAll()).array();
        QCOMPARE(turns.size(), 3);
        QCOMPARE(turns.at(0).toObject().value(QStringLiteral("role")).toString(), QStringLiteral("you"));
        QCOMPARE(turns.at(1).toObject().value(QStringLiteral("role")).toString(), QStringLiteral("bot"));
    }
    QVERIFY(backend.applyProposal());
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    QVERIFY2(backend.pace() == QLatin1String("frenzied"), qPrintable(backend.status()));
    QCOMPARE(backend.intent(), QStringLiteral("A frenzied cut."));
    QVERIFY(!lineById(backend.selects(), 2).value(QStringLiteral("keep")).toBool());
    QCOMPARE(readRoot().value(QStringLiteral("tighten")).toObject().value(QStringLiteral("max_pause")).toDouble(),
             0.1);
    QVERIFY(secondArgs.contains(QStringLiteral("--pace")));
    QCOMPARE(secondArgs.at(secondArgs.indexOf(QStringLiteral("--pace")) + 1), QStringLiteral("tight"));
    QCOMPARE(secondArgs.at(secondArgs.lastIndexOf(QStringLiteral("--")) + 1),
             QStringLiteral("keep going"));
    QVERIFY(!secondArgs.contains(QStringLiteral("--max-pause")));
    QVERIFY(!secondArgs.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    backend.revertRevise();
    QCOMPARE(backend.pace(), QStringLiteral("tight"));
    QCOMPARE(backend.maxPause(), 0.28);
    QCOMPARE(backend.intent(), QStringLiteral("Hand edit"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("off"));
    QVERIFY(lineById(backend.selects(), 2).value(QStringLiteral("keep")).toBool());
    QVERIFY(!backend.canRevert());
    QCOMPARE(backend.chat().size(), 6);
    // A new note replaces a proposal that is still waiting, and Leave it drops one.
    QVERIFY(backend.sendRevise(QStringLiteral("drop it after all")));
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    QVERIFY(backend.proposalPending());
    backend.dismissProposal();
    QVERIFY(!backend.proposalPending());
    QVERIFY(!QFileInfo::exists(QDir(out).filePath(QStringLiteral("proposal.json"))));
    QVERIFY(!backend.applyProposal());
    QCOMPARE(backend.chat().size(), 8);
    QCOMPARE(readRoot().value(QStringLiteral("tighten")).toObject().value(QStringLiteral("max_pause")).toDouble(),
             0.1);

    backend.setPace(QStringLiteral("open"));
    backend.setSceneTransition(QStringLiteral("dip"));
}

void BackendTests::cardLandsAtTheEndsOfTheTray() {
    EnvVarGuard keyGuard("XAI_API_KEY");
    EnvVarGuard fakeGuard("BOTCUT_FAKE");
    EnvVarGuard dataGuard("XDG_DATA_HOME");
    qunsetenv("XAI_API_KEY");
    qputenv("BOTCUT_FAKE", "1");
    qputenv("XDG_DATA_HOME", m_dir.path().toUtf8());

    QString cardRoot;
    QCOMPARE(ensureCardDirectory(&cardRoot), QString());
    const QString openShape = QDir(cardRoot).filePath(QStringLiteral("botcut-card-1-open.mp4"));
    const QString sentence = QStringLiteral("A quiet ride");
    const CutLaunch shaped = cutCardLaunch(openShape, sentence, QStringLiteral("/usr/bin/botcut-cli"),
                                           QString(), QString());
    QCOMPARE(shaped.arguments,
             (QStringList{QStringLiteral("card"), QStringLiteral("--out"), openShape,
                          QStringLiteral("--"), sentence}));
    QVERIFY(!shaped.arguments.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    QVERIFY(!shaped.arguments.contains(QStringLiteral("XAI_API_KEY")));
    const CutLaunch outside = cutCardLaunch(QStringLiteral("/tmp/botcut-card-1-open.mp4"), sentence,
                                             QStringLiteral("/usr/bin/botcut-cli"), QString(),
                                             QString());
    QCOMPARE(outside.error, QStringLiteral("No card file"));
    const QString closeShape = QDir(cardRoot).filePath(QStringLiteral("botcut-card-2-close.mp4"));
    const CutLaunch helpSentence = cutCardLaunch(closeShape, QStringLiteral("--help"),
                                                 QStringLiteral("/usr/bin/botcut-cli"), QString(),
                                                 QString());
    QCOMPARE(helpSentence.arguments.at(helpSentence.arguments.lastIndexOf(QStringLiteral("--")) + 1),
             QStringLiteral("--help"));
    const CutLaunch blank = cutCardLaunch(openShape, QStringLiteral("  "),
                                           QStringLiteral("/usr/bin/botcut-cli"), QString(), QString());
    QCOMPARE(blank.error, QStringLiteral("Say what the card says"));
    const CutLaunch badName = cutCardLaunch(QStringLiteral("/tmp/clip.mp4"), sentence,
                                             QStringLiteral("/usr/bin/botcut-cli"), QString(), QString());
    QCOMPARE(badName.error, QStringLiteral("No card file"));

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.setApiKey(QStringLiteral("supersecret"));
    backend.setIntent(sentence);
    const QString first = m_dir.filePath(QStringLiteral("card-a.mp4"));
    const QString second = m_dir.filePath(QStringLiteral("card-b.mp4"));
    QVERIFY(QFile(first).open(QIODevice::WriteOnly));
    QVERIFY(QFile(second).open(QIODevice::WriteOnly));
    backend.m_tray = {QFileInfo(first).absoluteFilePath(), QFileInfo(second).absoluteFilePath()};
    backend.m_trayIndex = 0;
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("clip"), 0);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("reason"), QStringLiteral("story"));
    line.insert(QStringLiteral("text"), QStringLiteral("hello"));
    QVariantList selects;
    selects.append(line);
    backend.m_selects = selects;

    backend.m_busy = true;
    QVERIFY(!backend.makeCard(QStringLiteral("open"), sentence));
    backend.m_busy = false;
    QCOMPARE(backend.tray(),
             (QStringList{QFileInfo(first).absoluteFilePath(), QFileInfo(second).absoluteFilePath()}));

    backend.m_launchProgram = m_dir.filePath(QStringLiteral("no-such-botcut-cli"));
    QVERIFY(backend.makeCard(QStringLiteral("open"), sentence));
    QTRY_VERIFY(!backend.busy());
    QVERIFY(backend.status().startsWith(QStringLiteral("Could not start")));
    QCOMPARE(backend.tray().size(), 2);
    QCOMPARE(backend.selects().size(), 1);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("clip")).toInt(), 0);
    QVERIFY(!backend.status().contains(QStringLiteral("supersecret")));
    backend.m_launchProgram.clear();
    backend.m_undoSelects = backend.m_selects;
    QVariantMap cover;
    cover.insert(QStringLiteral("clip"), 1);
    cover.insert(QStringLiteral("line"), 1);
    cover.insert(QStringLiteral("start"), 2.0);
    cover.insert(QStringLiteral("end"), 5.0);
    backend.m_covers = {cover};
    backend.m_undoCovers = {cover};
    backend.m_cutOut = m_dir.filePath(QStringLiteral("cut-out"));
    QVERIFY(QDir().mkpath(backend.m_cutOut));
    QFile cutsFile(QDir(backend.m_cutOut).filePath(QStringLiteral("cuts.json")));
    QVERIFY(cutsFile.open(QIODevice::WriteOnly));
    const QString cutsJson = QStringLiteral(
        "{\"clips\":[{\"index\":0,\"path\":\"%1\",\"duration\":1},{\"index\":1,\"path\":\"%2\",\"duration\":1}],"
        "\"lines\":[{\"id\":1,\"clip\":0,\"start\":0,\"end\":1,\"text\":\"hello\",\"keep\":true,\"reason\":\"story\"}],"
        "\"segments\":[{\"clip\":0,\"start\":0,\"end\":1,\"reason\":\"story\"}],"
        "\"covers\":[{\"clip\":1,\"line\":1,\"start\":2.0,\"end\":5.0}]}")
                                 .arg(QFileInfo(first).absoluteFilePath(),
                                      QFileInfo(second).absoluteFilePath());
    QCOMPARE(cutsFile.write(cutsJson.toUtf8()), qint64(cutsJson.toUtf8().size()));
    cutsFile.close();
    const QDir work(QDir(backend.m_cutOut).filePath(QStringLiteral("work")));
    QVERIFY(work.mkpath(QStringLiteral("stills")));
    const auto plant = [&](const QString &name, const QByteArray &body) {
        QFile file(work.filePath(name));
        return file.open(QIODevice::WriteOnly) && file.write(body) == qint64(body.size());
    };
    const QByteArray wordsBody("{\"words\":[{\"text\":\"hello\"}]}");
    const QByteArray silencesBody("[[0.1,0.4]]");
    QVERIFY(plant(QStringLiteral("0-card-a.fake.words.json"), wordsBody));
    QVERIFY(plant(QStringLiteral("0-card-a.silences.json"), silencesBody));
    QVERIFY(plant(QStringLiteral("0-card-a.flac"), QByteArray("flac")));
    QVERIFY(plant(QStringLiteral("1-card-b.fake.words.json"), QByteArray("{\"words\":[{\"text\":\"there\"}]}")));
    QVERIFY(plant(QStringLiteral("1-card-b.silences.json"), QByteArray("[[0.2,0.5]]")));
    QVERIFY(plant(QStringLiteral("notes.txt"), QByteArray("keep")));
    QVERIFY(plant(QStringLiteral("stills/3.jpg"), QByteArray("still")));

    QStringList statuses;
    const QMetaObject::Connection watch = connect(&backend, &Backend::statusChanged, &backend, [&] {
        statuses.append(backend.status());
    });
    QVERIFY2(backend.makeCard(QStringLiteral("open"), sentence), qPrintable(backend.status()));
    if (backend.busy())
        QCOMPARE(backend.status(), QStringLiteral("Making the card…"));
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    disconnect(watch);
    QVERIFY2(statuses.contains(QStringLiteral("Making the card…"))
                 || backend.status() == QLatin1String("Making the card…"),
             qPrintable(statuses.join(QStringLiteral(" | "))));
    QCOMPARE(backend.tray().size(), 3);
    const QString openCard = backend.tray().first();
    const QRegularExpression cardName(
        QStringLiteral("^botcut-card-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-open\\.mp4$"));
    QVERIFY(cardName.match(QFileInfo(openCard).fileName()).hasMatch());
    QCOMPARE(QFileInfo(openCard).dir().canonicalPath(), cardRoot);
    QVERIFY(QFileInfo(openCard).size() > 0);
    QCOMPARE(backend.tray().at(1), QFileInfo(first).absoluteFilePath());
    QCOMPARE(backend.tray().at(2), QFileInfo(second).absoluteFilePath());
    QCOMPARE(backend.selects().size(), 1);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("clip")).toInt(), 1);
    QCOMPARE(backend.m_undoSelects.at(0).toMap().value(QStringLiteral("clip")).toInt(), 1);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("clip")).toInt(), 2);
    QCOMPARE(backend.m_undoCovers.at(0).toMap().value(QStringLiteral("clip")).toInt(), 2);
    // The window is inside the B-roll file, so a shifted clip index leaves it alone.
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("start")).toDouble(), 2.0);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("end")).toDouble(), 5.0);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QVERIFY(cutsFile.open(QIODevice::ReadOnly));
    const QJsonObject cutsRoot = QJsonDocument::fromJson(cutsFile.readAll()).object();
    cutsFile.close();
    const QJsonArray cutsClips = cutsRoot.value(QStringLiteral("clips")).toArray();
    QCOMPARE(cutsClips.size(), 3);
    QCOMPARE(cutsClips.at(0).toObject().value(QStringLiteral("path")).toString(), openCard);
    QCOMPARE(cutsClips.at(1).toObject().value(QStringLiteral("path")).toString(),
             QFileInfo(first).absoluteFilePath());
    QCOMPARE(cutsRoot.value(QStringLiteral("lines")).toArray().at(0).toObject().value(QStringLiteral("clip")).toInt(),
             1);
    QCOMPARE(cutsRoot.value(QStringLiteral("segments")).toArray().at(0).toObject().value(QStringLiteral("clip")).toInt(),
             1);
    QCOMPARE(cutsRoot.value(QStringLiteral("covers")).toArray().at(0).toObject().value(QStringLiteral("clip")).toInt(),
             2);
    QCOMPARE(cutsRoot.value(QStringLiteral("covers")).toArray().at(0).toObject().value(QStringLiteral("start")).toDouble(),
             2.0);
    QCOMPARE(cutsRoot.value(QStringLiteral("covers")).toArray().at(0).toObject().value(QStringLiteral("end")).toDouble(),
             5.0);
    QVERIFY(!work.exists(QStringLiteral("0-card-a.fake.words.json")));
    QVERIFY(!work.exists(QStringLiteral("0-card-a.silences.json")));
    QVERIFY(!work.exists(QStringLiteral("0-card-a.flac")));
    QVERIFY(!work.exists(QStringLiteral("1-card-b.fake.words.json")));
    QFile shiftedWords(work.filePath(QStringLiteral("1-card-a.fake.words.json")));
    QVERIFY(shiftedWords.open(QIODevice::ReadOnly));
    QCOMPARE(shiftedWords.readAll(), wordsBody);
    QFile shiftedSilences(work.filePath(QStringLiteral("1-card-a.silences.json")));
    QVERIFY(shiftedSilences.open(QIODevice::ReadOnly));
    QCOMPARE(shiftedSilences.readAll(), silencesBody);
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("1-card-a.flac"))).isFile());
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("2-card-b.fake.words.json"))).isFile());
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("2-card-b.silences.json"))).isFile());
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("notes.txt"))).isFile());
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("stills/3.jpg"))).isFile());
    QVERIFY(backend.m_cutProcess);
    const QStringList openArgs = backend.m_cutProcess->arguments();
    QVERIFY(openArgs.contains(QStringLiteral("card")));
    QCOMPARE(openArgs.at(openArgs.lastIndexOf(QStringLiteral("--")) + 1), sentence);
    QVERIFY(!openArgs.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    QVERIFY(!openArgs.contains(QStringLiteral("XAI_API_KEY")));
    QCOMPARE(backend.m_cutProcess->processEnvironment().value(QStringLiteral("XAI_API_KEY")),
             QStringLiteral("supersecret"));
    QCOMPARE(backend.m_cutProcess->processEnvironment().value(QStringLiteral("BOTCUT_FAKE")),
             QStringLiteral("1"));
    QVERIFY(!backend.status().contains(QStringLiteral("supersecret")));

    QVERIFY2(backend.makeCard(QStringLiteral("close"), sentence), qPrintable(backend.status()));
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    QCOMPARE(backend.tray().size(), 4);
    QCOMPARE(backend.tray().first(), openCard);
    const QString closeCard = backend.tray().last();
    QVERIFY(closeCard != openCard);
    QVERIFY(QFileInfo(closeCard).fileName().startsWith(QStringLiteral("botcut-card-")));
    QVERIFY(QFileInfo(closeCard).fileName().endsWith(QStringLiteral("-close.mp4")));
    QCOMPARE(QFileInfo(closeCard).dir().canonicalPath(), cardRoot);
    QVERIFY(QFileInfo(closeCard).size() > 0);
    QCOMPARE(backend.tray().at(1), QFileInfo(first).absoluteFilePath());
    QCOMPARE(backend.tray().at(2), QFileInfo(second).absoluteFilePath());
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("clip")).toInt(), 1);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("clip")).toInt(), 2);
    QVERIFY(cutsFile.open(QIODevice::ReadOnly));
    QCOMPARE(QJsonDocument::fromJson(cutsFile.readAll()).object().value(QStringLiteral("covers")).toArray().at(0).toObject().value(QStringLiteral("clip")).toInt(),
             2);
    cutsFile.close();
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("1-card-a.fake.words.json"))).isFile());
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("1-card-a.silences.json"))).isFile());
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("2-card-b.fake.words.json"))).isFile());
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("2-card-b.silences.json"))).isFile());
    QVERIFY(!work.exists(QStringLiteral("2-card-a.fake.words.json")));
    QVERIFY(!work.exists(QStringLiteral("3-card-b.fake.words.json")));
    QVERIFY(QFileInfo(work.filePath(QStringLiteral("stills/3.jpg"))).isFile());
    const QStringList closeArgs = backend.m_cutProcess->arguments();
    QVERIFY(closeArgs.contains(QStringLiteral("card")));
    QCOMPARE(closeArgs.at(closeArgs.lastIndexOf(QStringLiteral("--")) + 1), sentence);
    QVERIFY(!closeArgs.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    QVERIFY(!closeArgs.contains(QStringLiteral("XAI_API_KEY")));
    QCOMPARE(backend.selects().size(), 1);

    QVERIFY(QFile::setPermissions(work.path(), QFileDevice::ReadOwner | QFileDevice::ExeOwner));
    const int trayBefore = backend.tray().size();
    const int coverClip = backend.covers().at(0).toMap().value(QStringLiteral("clip")).toInt();
    QVERIFY2(backend.makeCard(QStringLiteral("open"), sentence), qPrintable(backend.status()));
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    QCOMPARE(backend.status(), QStringLiteral("Could not save the line list"));
    QCOMPARE(backend.tray().size(), trayBefore);
    QCOMPARE(backend.covers().at(0).toMap().value(QStringLiteral("clip")).toInt(), coverClip);
    QCOMPARE(backend.m_undoCovers.at(0).toMap().value(QStringLiteral("clip")).toInt(), coverClip);
    QVERIFY(QFile::setPermissions(work.path(),
                                  QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));

    backend.setPace(QStringLiteral("open"));
    backend.setSceneTransition(QStringLiteral("dip"));
}

void BackendTests::helpNoteDoesNotReplayRevise() {
    EnvVarGuard keyGuard("XAI_API_KEY");
    EnvVarGuard fakeGuard("BOTCUT_FAKE");
    qunsetenv("XAI_API_KEY");
    qunsetenv("BOTCUT_FAKE");

    const CutLaunch shaped = cutReviseLaunch(
        QStringLiteral("/tmp/out/cuts.json"), QStringLiteral("--help"),
        QStringLiteral("/usr/bin/botcut-cli"), QString(), QString(), QStringLiteral("measured"),
        QStringLiteral("dip"));
    QCOMPARE(shaped.arguments.at(shaped.arguments.lastIndexOf(QStringLiteral("--")) + 1),
             QStringLiteral("--help"));
    QVERIFY(shaped.arguments.indexOf(QStringLiteral("--help"))
            > shaped.arguments.indexOf(QStringLiteral("--pace")));

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.setIntent(QStringLiteral("A quiet ride"));
    backend.setPace(QStringLiteral("measured"));
    backend.setSceneTransition(QStringLiteral("dip"));

    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("clip"), 0);
    line.insert(QStringLiteral("start"), 0.2);
    line.insert(QStringLiteral("end"), 1.2);
    line.insert(QStringLiteral("text"), QStringLiteral("hello there"));
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("reason"), QStringLiteral("story"));
    QVariantList selects;
    selects.append(line);
    backend.m_selects = selects;

    const QString out = m_dir.filePath(QStringLiteral("revise-help"));
    QVERIFY(QDir().mkpath(out));
    backend.m_cutOut = out;
    QJsonObject revise;
    revise.insert(QStringLiteral("pace"), QStringLiteral("frenzied"));
    revise.insert(QStringLiteral("dip"), false);
    revise.insert(QStringLiteral("deliver"), QStringLiteral("render"));
    QJsonObject root;
    QJsonObject tighten;
    tighten.insert(QStringLiteral("max_pause"), 0.8);
    root.insert(QStringLiteral("intent"), QStringLiteral("A quiet ride"));
    root.insert(QStringLiteral("tighten"), tighten);
    root.insert(QStringLiteral("lines"), QJsonArray());
    root.insert(QStringLiteral("revise"), revise);
    const QString cuts = QDir(out).filePath(QStringLiteral("cuts.json"));
    {
        QFile file(cuts);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Indented);
        QCOMPARE(file.write(bytes), bytes.size());
    }

    QVERIFY2(backend.sendRevise(QStringLiteral("--help")), qPrintable(backend.status()));
    QCOMPARE(backend.chat().size(), 1);
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 60000);
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
    QCOMPARE(backend.intent(), QStringLiteral("A quiet ride"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));
    QVERIFY(!backend.canRevert());
    QVERIFY(!backend.proposalPending());
    QCOMPARE(backend.chat().size(), 0);
    QVERIFY(!QFileInfo::exists(QDir(out).filePath(QStringLiteral("proposal.json"))));
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QVERIFY(!backend.status().contains(QStringLiteral("supersecret")));
    QVERIFY(backend.status() != QLatin1String("Ready to render"));

    QVERIFY(backend.m_cutProcess);
    const QStringList args = backend.m_cutProcess->arguments();
    const int sep = args.lastIndexOf(QStringLiteral("--"));
    QVERIFY(sep >= 0);
    QCOMPARE(args.at(sep + 1), QStringLiteral("--help"));
    QVERIFY(!args.join(QLatin1Char(' ')).contains(QStringLiteral("supersecret")));
    QVERIFY(backend.m_cutProcess->processEnvironment().value(QStringLiteral("XAI_API_KEY")).isEmpty());
    QVERIFY(backend.m_cutProcess->processEnvironment().value(QStringLiteral("BOTCUT_FAKE")) != QLatin1String("1"));

    QFile stamped(cuts);
    QVERIFY(stamped.open(QIODevice::ReadOnly));
    backend.m_reviseStamp = stamped.readAll();
    stamped.close();
    QVERIFY(QJsonDocument::fromJson(backend.m_reviseStamp).object().value(QStringLiteral("revise")).toObject()
                .value(QStringLiteral("pace")).toString()
            == QLatin1String("frenzied"));
    backend.m_cutStage = Backend::CutStage::Revise;
    backend.m_reviseNote = QStringLiteral("--help");
    backend.m_busy = true;
    backend.cutProcessFinished(0, QProcess::NormalExit);
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
    QCOMPARE(backend.intent(), QStringLiteral("A quiet ride"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));
    QVERIFY(!backend.canRevert());
    QCOMPARE(backend.chat().size(), 0);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());

    backend.setPace(QStringLiteral("open"));
    backend.setSceneTransition(QStringLiteral("dip"));
}

void BackendTests::failedLaunchKeepsTheReviseSnapshot() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString clip = m_dir.filePath(QStringLiteral("launch-keep.mp4"));
    QVERIFY(QFile(clip).open(QIODevice::WriteOnly));
    backend.m_tray = {QFileInfo(clip).absoluteFilePath()};
    backend.m_cutMode = QStringLiteral("nope");
    backend.m_cutOut = QStringLiteral("/tmp/previous-cut");
    backend.setIntent(QStringLiteral("A quiet ride"));
    backend.setPace(QStringLiteral("measured"));
    backend.setSceneTransition(QStringLiteral("dip"));
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("reason"), QStringLiteral("story"));
    line.insert(QStringLiteral("text"), QStringLiteral("hello"));
    QVariantList selects;
    selects.append(line);
    backend.m_selects = selects;
    backend.m_undoSelects = selects;
    backend.m_undoIntent = QStringLiteral("A quiet ride");
    backend.m_undoPace = QStringLiteral("measured");
    backend.m_undoDip = QStringLiteral("dip");
    backend.m_canRevert = true;
    QVariantMap note;
    note.insert(QStringLiteral("role"), QStringLiteral("you"));
    note.insert(QStringLiteral("text"), QStringLiteral("drop the stumble"));
    backend.m_chat = {note};

    backend.startCut();
    QCOMPARE(backend.status(), QStringLiteral("Unknown cut mode"));
    QVERIFY(!backend.busy());
    QCOMPARE(backend.m_cutOut, QStringLiteral("/tmp/previous-cut"));
    QCOMPARE(backend.selects().size(), 1);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QVERIFY(backend.canRevert());
    QCOMPARE(backend.chat().size(), 1);
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
    QCOMPARE(backend.intent(), QStringLiteral("A quiet ride"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));

    backend.setPace(QStringLiteral("open"));
    backend.setSceneTransition(QStringLiteral("dip"));
}

void BackendTests::missingProgramKeepsTheReviseSnapshot() {
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString clip = m_dir.filePath(QStringLiteral("missing-prog.mp4"));
    QVERIFY(QFile(clip).open(QIODevice::WriteOnly));
    backend.m_tray = {QFileInfo(clip).absoluteFilePath()};
    backend.m_cutMode = QStringLiteral("assemble");
    backend.m_cutOut = QStringLiteral("/tmp/previous-cut");
    backend.m_launchProgram = m_dir.filePath(QStringLiteral("no-such-botcut-cli"));
    QVERIFY(!QFileInfo::exists(backend.m_launchProgram));
    backend.setIntent(QStringLiteral("A quiet ride"));
    backend.setPace(QStringLiteral("measured"));
    backend.setSceneTransition(QStringLiteral("dip"));
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("reason"), QStringLiteral("story"));
    line.insert(QStringLiteral("text"), QStringLiteral("hello"));
    QVariantList selects;
    selects.append(line);
    backend.m_selects = selects;
    backend.m_undoSelects = selects;
    backend.m_undoIntent = QStringLiteral("A quiet ride");
    backend.m_undoPace = QStringLiteral("measured");
    backend.m_undoDip = QStringLiteral("dip");
    backend.m_canRevert = true;
    QVariantMap note;
    note.insert(QStringLiteral("role"), QStringLiteral("you"));
    note.insert(QStringLiteral("text"), QStringLiteral("drop the stumble"));
    backend.m_chat = {note};

    backend.startCut();
    QCOMPARE(backend.selects().size(), 1);
    QVERIFY(backend.canRevert());
    QCOMPARE(backend.chat().size(), 1);
    QTRY_VERIFY(!backend.busy());
    QCOMPARE(backend.m_cutOut, QStringLiteral("/tmp/previous-cut"));
    QCOMPARE(backend.selects().size(), 1);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QVERIFY(backend.canRevert());
    QCOMPARE(backend.chat().size(), 1);
    QCOMPARE(backend.pace(), QStringLiteral("measured"));
    QCOMPARE(backend.intent(), QStringLiteral("A quiet ride"));
    QCOMPARE(backend.sceneTransition(), QStringLiteral("dip"));
    QVERIFY(backend.status().startsWith(QStringLiteral("Could not start")));

    backend.setPace(QStringLiteral("open"));
    backend.setSceneTransition(QStringLiteral("dip"));
}

void BackendTests::cutStatusLines() {
    QCOMPARE(cutStatusFromLine(QStringLiteral("Reading files")), QStringLiteral("Reading files"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Reading pictures")), QStringLiteral("Reading pictures"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Trying again")), QStringLiteral("Trying again"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Transcribing 2/4 clip.MP4")),
             QStringLiteral("Transcribing 2/4 clip.MP4"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Choosing takes")), QStringLiteral("Choosing takes"));
    QCOMPARE(cutStatusFromLine(QStringLiteral("Revising")), QStringLiteral("Revising"));
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

void BackendTests::pickerSelectionLoadsVideo() {
    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QSignalSpy infoSpy(&backend, &Backend::infoChanged);
    QSignalSpy gatheringSpy(&backend, &Backend::gatheringChanged);
    QVERIFY(backend.gathering());

    QVERIFY(backend.load(videoUrl()));

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
    // The clip is square, so a swapped width and height would still match the probe.
    backend.m_info.width = 1920;
    backend.m_info.height = 1080;
    backend.exportDialog();

    QCOMPARE(picker->exportCount, 1);
    QCOMPARE(picker->lastSuggestedUrl,
             QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("clip_trimmed.mp4"))));
    QCOMPARE(picker->lastSourceWidth, 1920);
    QCOMPARE(picker->lastSourceHeight, 1080);
    QCOMPARE(picker->lastSourceWidth, backend.m_info.width);
    QCOMPARE(picker->lastSourceHeight, backend.m_info.height);
    QCOMPARE(picker->lastScaleHeights, Backend::exportHeights(backend.m_info.width, backend.m_info.height));
    QVERIFY(picker->lastScaleHeights != (QList<int>{1080, 720}));
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

    // ? toggles the hotkey overlay, and Escape closes it again.
    QTest::keyClick(window, Qt::Key_Question);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("helpVisible").toBool(), true, 3000);
    QTest::keyClick(window, Qt::Key_Escape);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("helpVisible").toBool(), false, 3000);

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

// Real media through the FFmpeg backend: the silent cover player puts the
// B-roll beat over the start of a covered line, then leaves when the beat ends.
void BackendTests::coverShowsInThePreview() {
    const QString talk = makeVideo(QStringLiteral("cover-talk.mp4"), 6.0, true);
    const QString room = makeVideo(QStringLiteral("cover-room.mp4"), 6.0, false);
    QVERIFY(!talk.isEmpty());
    QVERIFY(!room.isEmpty());
    ShortcutBackend backend(QUrl(), 0.0);
    backend.setTray({talk, room});
    backend.setCutClips({talk, room});
    backend.setPreviewUrl(QUrl::fromLocalFile(talk));
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("clip"), 0);
    line.insert(QStringLiteral("start"), 1.0);
    line.insert(QStringLiteral("end"), 5.0);
    line.insert(QStringLiteral("keep"), true);
    line.insert(QStringLiteral("text"), QStringLiteral("the ride"));
    backend.setSelects({line});
    QVariantMap cover;
    cover.insert(QStringLiteral("clip"), 1);
    cover.insert(QStringLiteral("line"), 1);
    cover.insert(QStringLiteral("through"), 1);
    cover.insert(QStringLiteral("start"), 1.0);
    cover.insert(QStringLiteral("end"), 3.0);
    cover.insert(QStringLiteral("reason"), QStringLiteral("the road"));
    backend.setCovers({cover});

    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(100);
    QCOMPARE(window->property("viewStep").toString(), QStringLiteral("lines"));
    QQuickItem *overlay = window->findChild<QQuickItem *>(QStringLiteral("coverOut"));
    QVERIFY(overlay);
    QVERIFY(!overlay->isVisible());
    QVERIFY(window->property("coverNow").isNull());

    QVERIFY(QMetaObject::invokeMethod(window, "playLine", Q_ARG(QVariant, QVariant(line)),
                                      Q_ARG(QVariant, QVariant(true)), Q_ARG(QVariant, QVariant())));
    QCOMPARE(window->property("linePlayStart").toInt(), 1000);
    // Inside the beat: the cover names the B-roll file, and its frame goes up.
    QTRY_VERIFY_WITH_TIMEOUT(!window->property("coverNow").isNull(), 6000);
    const QVariantMap now = window->property("coverNow").toMap();
    QCOMPARE(now.value(QStringLiteral("path")).toString(), room);
    QVERIFY(now.value(QStringLiteral("src")).toDouble() >= 1.0);
    QCOMPARE(now.value(QStringLiteral("until")).toDouble(), 3.0);
    QTRY_VERIFY_WITH_TIMEOUT(overlay->isVisible(), 6000);
    // The beat ends at 3 s into the line's file while the line plays on to 5 s.
    QTRY_VERIFY_WITH_TIMEOUT(window->property("coverNow").isNull(), 6000);
    QTRY_VERIFY_WITH_TIMEOUT(!overlay->isVisible(), 3000);
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

void BackendTests::qmlKeysRemoveAndRestoreClips() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));

    // S no longer splits. The clips here are cut in the model, at 5 s and then at 10 s.
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 5.0, 3000);
    QTest::keyClick(window, Qt::Key_S);
    QTest::qWait(50);
    QCOMPARE(backend.timeline.clips(), (edit::Clips{{0.0, 20.0}}));
    backend.timeline.split(5.0);
    QCOMPARE(backend.timeline.clips(), (edit::Clips{{0.0, 5.0}, {5.0, 20.0}}));
    QCOMPARE(window->property("unexported").toBool(), false);
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 10.0, 3000);
    backend.timeline.split(10.0);
    QCOMPARE(backend.timeline.clips(), (edit::Clips{{0.0, 5.0}, {5.0, 10.0}, {10.0, 20.0}}));

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
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 10.0, 3000);
    backend.timeline.split(10.0);
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

void BackendTests::qmlPlainMovieLocksTrimWhileBusy() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));
    QQuickItem *editBar = harness.editBar();
    QVERIFY(editBar);
    QVERIFY(editBar->isVisible());
    QVERIFY(!backend.planCut());
    QVERIFY(editBar->isEnabled());
    QCOMPARE(window->property("editing").toBool(), true);
    QVERIFY(qAbs(editBar->opacity() - 1.0) < 0.01);
    // y used to be -height - 8, which painted the chip over Play.
    QTRY_VERIFY_WITH_TIMEOUT(editBar->height() >= 76.0, 3000);
    QQuickItem *hint = editBar->findChild<QQuickItem *>(QStringLiteral("filmstripHint"));
    QVERIFY(hint);
    QVERIFY(hint->parentItem() == editBar);
    QVERIFY2(hint->y() >= 0.0, qPrintable(QString::number(hint->y())));
    QVERIFY2(hint->y() + hint->height() <= editBar->height() + 0.5,
             qPrintable(QStringLiteral("%1 + %2 > %3")
                            .arg(hint->y())
                            .arg(hint->height())
                            .arg(editBar->height())));

    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), 5.0, 3000);
    backend.timeline.split(5.0);
    QCOMPARE(backend.timeline.clips(), (edit::Clips{{0.0, 5.0}, {5.0, 20.0}}));

    backend.setBusy(true);
    QTest::qWait(50);
    QVERIFY(!editBar->isEnabled());
    QVERIFY(qAbs(editBar->opacity() - 0.45) < 0.01);
    QCOMPARE(window->property("editing").toBool(), false);

    const edit::Clips frozen = backend.timeline.clips();
    const double head = playhead(harness);
    QTest::keyClick(window, Qt::Key_X);
    QTest::keyClick(window, Qt::Key_Space, Qt::ControlModifier);
    QTest::keyClick(window, Qt::Key_Space, Qt::AltModifier);
    QTest::keyClick(window, Qt::Key_Right);
    QTest::keyClick(window, Qt::Key_Z, Qt::ControlModifier);
    QTest::qWait(50);
    QCOMPARE(backend.timeline.clips(), frozen);
    QCOMPARE(playhead(harness), head);

    backend.setBusy(false);
    QTest::qWait(50);
    QVERIFY(editBar->isEnabled());
    QCOMPARE(window->property("editing").toBool(), true);
    QVERIFY(qAbs(editBar->opacity() - 1.0) < 0.01);
    // The keys work again: the playhead moves and X takes the clip under it.
    QTest::keyClick(window, Qt::Key_Right, Qt::ShiftModifier);
    QTRY_COMPARE_WITH_TIMEOUT(playhead(harness), head + 5.0, 3000);
    QTest::keyClick(window, Qt::Key_X);
    QTRY_COMPARE_WITH_TIMEOUT(backend.timeline.clips(), (edit::Clips{{0.0, 5.0}}), 3000);
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
    QQuickItem *cancelButton = dialogButton(window, QStringLiteral("Keep working"));
    QVERIFY(cancelButton);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(cancelButton));
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), false, 3000);
    QCOMPARE(backend.exportCount, 1);

    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QQuickItem *exportButton = dialogButton(window, QStringLiteral("Export…"));
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
    QVERIFY(dialogButton(window, QStringLiteral("Save…")));
    QVERIFY(dialogButton(window, QStringLiteral("Quit without saving")));

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

void BackendTests::qmlQuitAsksWhileAJobIsRunning() {
    ShortcutBackend backend(QUrl::fromLocalFile(m_dir.filePath(QStringLiteral("shortcut-placeholder.mp4"))),
                            20.0);
    backend.setBusy(true);
    QmlHarness harness(backend);
    QQuickWindow *window = showEditor(harness, backend);
    QVERIFY2(window, qPrintable(mainQmlPath()));
    QCOMPARE(window->property("unexported").toBool(), false);
    QCOMPARE(window->property("looseCut").toBool(), false);

    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    QVERIFY(dialogButton(window, QStringLiteral("Keep working")));
    QQuickItem *stop = visibleItemWithText(window, QStringLiteral("Stop and quit"));
    QVERIFY(stop);

    // Enter keeps working. The running job is not the button that takes focus.
    QTest::keyClick(window, Qt::Key_Return);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), false, 3000);
    QVERIFY(window->isVisible());

    QSignalSpy quitSpy(&harness.engine(), &QQmlApplicationEngine::quit);
    QTest::keyClick(window, Qt::Key_Q);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("quitConfirmVisible").toBool(), true, 3000);
    stop = visibleItemWithText(window, QStringLiteral("Stop and quit"));
    QVERIFY(stop);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(stop));
    QTRY_VERIFY_WITH_TIMEOUT(!window->isVisible(), 3000);
    QCOMPARE(quitSpy.count(), 1);
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

void BackendTests::renderedCutRefusesAnUpscale() {
    const QString seed = makeVideo(QStringLiteral("seed-no-upscale.mp4"), 1.0, false);
    QVERIFY(!seed.isEmpty());
    const QString dirPath = QDir::temp().filePath(QStringLiteral("botcut-cut-noscale-test"));
    QVERIFY(QDir().mkpath(dirPath));
    const QString rough = QDir(dirPath).filePath(QStringLiteral("rough_cut.mp4"));
    QFile::remove(rough);
    QVERIFY(QFile::copy(seed, rough));

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QVERIFY(backend.load(QUrl::fromLocalFile(rough)));
    QVERIFY(backend.renderedUnsaved());

    const QString saved = m_dir.filePath(QStringLiteral("saved-no-upscale.mp4"));
    QFile::remove(saved);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);
    // 32×32 is already below 720p. The choice must copy, not grow the frame.
    emit picker->exportSelected(QUrl::fromLocalFile(saved), 720);
    QTRY_COMPARE_WITH_TIMEOUT(doneSpy.count(), 1, 5000);
    QCOMPARE(failedSpy.count(), 0);
    QFile savedFile(saved);
    QFile roughFile(rough);
    QVERIFY(savedFile.open(QIODevice::ReadOnly));
    QVERIFY(roughFile.open(QIODevice::ReadOnly));
    QCOMPARE(savedFile.readAll(), roughFile.readAll());
    QVERIFY(!backend.renderedUnsaved());
    QCOMPARE(backend.source(), QUrl::fromLocalFile(saved));
    QVERIFY(QFileInfo::exists(rough));
    QDir(dirPath).removeRecursively();
}

void BackendTests::renderedCutDownscalesToTheChosenSize() {
    const QString ffmpegBin = QStandardPaths::findExecutable(QStringLiteral("ffmpeg"));
    QVERIFY(!ffmpegBin.isEmpty());
    const QString seed = m_dir.filePath(QStringLiteral("seed-downscale.mp4"));
    QProcess make;
    make.start(ffmpegBin, {
        QStringLiteral("-hide_banner"), QStringLiteral("-loglevel"), QStringLiteral("error"),
        QStringLiteral("-f"), QStringLiteral("lavfi"),
        QStringLiteral("-i"), QStringLiteral("testsrc=size=320x180:rate=30:duration=1"),
        QStringLiteral("-pix_fmt"), QStringLiteral("yuv420p"),
        QStringLiteral("-y"), seed,
    });
    QVERIFY(make.waitForFinished(15000));
    QCOMPARE(make.exitCode(), 0);

    const QString dirPath = QDir::temp().filePath(QStringLiteral("botcut-cut-downscale-test"));
    QDir(dirPath).removeRecursively();
    QVERIFY(QDir().mkpath(dirPath));
    const QString rough = QDir(dirPath).filePath(QStringLiteral("rough_cut.mp4"));
    QVERIFY(QFile::copy(seed, rough));
    QFile cuts(QDir(dirPath).filePath(QStringLiteral("cuts.json")));
    QVERIFY(cuts.open(QIODevice::WriteOnly | QIODevice::Truncate));
    cuts.write("{}\n");
    cuts.close();
    const QString srtBody = QStringLiteral("1\n00:00:00,000 --> 00:00:01,000\nHello\n");
    QFile srt(QDir(dirPath).filePath(QStringLiteral("rough_cut.srt")));
    QVERIFY(srt.open(QIODevice::WriteOnly | QIODevice::Truncate));
    srt.write(srtBody.toUtf8());
    srt.close();

    ThumbProvider provider;
    auto *picker = new FakeFilePicker;
    Backend backend(&provider, picker);
    QVERIFY(backend.load(QUrl::fromLocalFile(rough)));
    QVERIFY(backend.renderedUnsaved());
    QVERIFY(backend.roughCut());

    const QString saved = m_dir.filePath(QStringLiteral("saved-downscale.mp4"));
    const QString savedSrt = m_dir.filePath(QStringLiteral("saved-downscale.srt"));
    QFile::remove(saved);
    QFile::remove(savedSrt);
    QSignalSpy doneSpy(&backend, &Backend::exportDone);
    QSignalSpy failedSpy(&backend, &Backend::exportFailed);
    emit picker->exportSelected(QUrl::fromLocalFile(saved), 90);
    QTRY_COMPARE_WITH_TIMEOUT(doneSpy.count() + failedSpy.count(), 1, 20000);
    QVERIFY2(failedSpy.isEmpty(),
             qPrintable(failedSpy.isEmpty() ? QString() : failedSpy.first().first().toString()));
    QCOMPARE(doneSpy.count(), 1);

    const ffmpeg::VideoInfo info = ffmpeg::probe(saved);
    QVERIFY(info.ok);
    QCOMPARE(info.width, 160);
    QCOMPARE(info.height, 90);
    QFile savedFile(saved);
    QFile roughFile(rough);
    QVERIFY(savedFile.open(QIODevice::ReadOnly));
    QVERIFY(roughFile.open(QIODevice::ReadOnly));
    QVERIFY(savedFile.readAll() != roughFile.readAll());
    QVERIFY(QFileInfo::exists(rough));
    QCOMPARE(backend.source(), QUrl::fromLocalFile(saved));
    QVERIFY(!backend.renderedUnsaved());
    QVERIFY(backend.roughCut());
    QVERIFY(backend.status().isEmpty());
    QFile copied(savedSrt);
    QVERIFY(copied.open(QIODevice::ReadOnly));
    QCOMPARE(QString::fromUtf8(copied.readAll()), srtBody);
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
    QVERIFY(backend.roughCut());
    QVERIFY(backend.status().isEmpty());
    QVERIFY(backend.load(QUrl::fromLocalFile(seed)));
    QVERIFY(!backend.roughCut());
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

void BackendTests::planWatchTrimsOneSourceAndRenders() {
    EnvVarGuard keyGuard("XAI_API_KEY");
    EnvVarGuard fakeGuard("BOTCUT_FAKE");
    qunsetenv("XAI_API_KEY");
    qputenv("BOTCUT_FAKE", "1");

    const QString fileA = makeVideo(QStringLiteral("plan-a.mp4"), 8.0, false);
    const QString fileB = makeVideo(QStringLiteral("plan-b.mp4"), 6.0, false);
    const QString seed = makeVideo(QStringLiteral("plan-seed.mp4"), 1.0, false);
    QVERIFY(!fileA.isEmpty());
    QVERIFY(!fileB.isEmpty());
    QVERIFY(!seed.isEmpty());

    const QString dirPath = QDir::temp().filePath(QStringLiteral("botcut-cut-plan-watch"));
    QDir(dirPath).removeRecursively();
    QVERIFY(QDir().mkpath(dirPath));
    const QString rough = QDir(dirPath).filePath(QStringLiteral("rough_cut.mp4"));
    QVERIFY(QFile::copy(seed, rough));
    const QString cutsPath = QDir(dirPath).filePath(QStringLiteral("cuts.json"));

    QJsonObject clipA;
    clipA.insert(QStringLiteral("index"), 0);
    clipA.insert(QStringLiteral("path"), fileA);
    clipA.insert(QStringLiteral("duration"), 8.0);
    QJsonObject clipB;
    clipB.insert(QStringLiteral("index"), 2);
    clipB.insert(QStringLiteral("path"), fileB);
    clipB.insert(QStringLiteral("duration"), 6.0);
    QJsonArray clips;
    clips.append(clipA);
    clips.append(clipB);
    QJsonObject segA;
    segA.insert(QStringLiteral("clip"), 0);
    segA.insert(QStringLiteral("start"), 1.0);
    segA.insert(QStringLiteral("end"), 5.0);
    segA.insert(QStringLiteral("reason"), QStringLiteral("story"));
    segA.insert(QStringLiteral("note"), QStringLiteral("keep"));
    QJsonObject segB;
    // Clip 2 on segment 1. A hit that copies the segment index into clip still says 1.
    segB.insert(QStringLiteral("clip"), 2);
    segB.insert(QStringLiteral("start"), 0.5);
    segB.insert(QStringLiteral("end"), 3.5);
    segB.insert(QStringLiteral("reason"), QStringLiteral("wide"));
    QJsonArray segments;
    segments.append(segA);
    segments.append(segB);
    // Against source [1, 5), hello is the greatest overlap and the earlier start.
    // long is the longest line, later is the first equal overlap, second copies
    // hello's range, after is the last equal overlap, and early is the earliest
    // start with the segment's reason and a smaller overlap.
    QJsonObject longLine;
    longLine.insert(QStringLiteral("id"), 2);
    longLine.insert(QStringLiteral("clip"), 0);
    longLine.insert(QStringLiteral("start"), 4.0);
    longLine.insert(QStringLiteral("end"), 8.0);
    longLine.insert(QStringLiteral("text"), QStringLiteral("long"));
    longLine.insert(QStringLiteral("keep"), true);
    QJsonObject later;
    later.insert(QStringLiteral("id"), 3);
    later.insert(QStringLiteral("clip"), 0);
    later.insert(QStringLiteral("start"), 3.0);
    later.insert(QStringLiteral("end"), 5.5);
    later.insert(QStringLiteral("text"), QStringLiteral("later"));
    later.insert(QStringLiteral("keep"), true);
    QJsonObject line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("clip"), 0);
    line.insert(QStringLiteral("start"), 0.5);
    line.insert(QStringLiteral("end"), 3.0);
    line.insert(QStringLiteral("text"), QStringLiteral("hello"));
    line.insert(QStringLiteral("keep"), true);
    QJsonObject duplicate;
    duplicate.insert(QStringLiteral("id"), 5);
    duplicate.insert(QStringLiteral("clip"), 0);
    duplicate.insert(QStringLiteral("start"), 0.5);
    duplicate.insert(QStringLiteral("end"), 3.0);
    duplicate.insert(QStringLiteral("text"), QStringLiteral("second"));
    duplicate.insert(QStringLiteral("keep"), true);
    QJsonObject after;
    after.insert(QStringLiteral("id"), 6);
    after.insert(QStringLiteral("clip"), 0);
    after.insert(QStringLiteral("start"), 2.5);
    after.insert(QStringLiteral("end"), 4.5);
    after.insert(QStringLiteral("text"), QStringLiteral("after"));
    after.insert(QStringLiteral("keep"), true);
    QJsonObject early;
    early.insert(QStringLiteral("id"), 7);
    early.insert(QStringLiteral("clip"), 0);
    early.insert(QStringLiteral("start"), 0.0);
    early.insert(QStringLiteral("end"), 1.4);
    early.insert(QStringLiteral("text"), QStringLiteral("early"));
    early.insert(QStringLiteral("keep"), true);
    early.insert(QStringLiteral("reason"), QStringLiteral("story"));
    QJsonObject missed;
    missed.insert(QStringLiteral("id"), 4);
    missed.insert(QStringLiteral("clip"), 1);
    missed.insert(QStringLiteral("start"), 0.0);
    missed.insert(QStringLiteral("end"), 0.5);
    missed.insert(QStringLiteral("text"), QStringLiteral("touch"));
    missed.insert(QStringLiteral("keep"), true);
    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("mode"), QStringLiteral("speech"));
    root.insert(QStringLiteral("intent"), QStringLiteral("A quiet ride"));
    root.insert(QStringLiteral("clips"), clips);
    root.insert(QStringLiteral("segments"), segments);
    root.insert(QStringLiteral("lines"), QJsonArray{longLine, later, line, duplicate, after, early, missed});
    root.insert(QStringLiteral("dropped"), QJsonArray());
    {
        QFile file(cutsPath);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Indented);
        QCOMPARE(file.write(bytes), bytes.size());
    }

    const auto readRoot = [&cutsPath] {
        QFile in(cutsPath);
        if (!in.open(QIODevice::ReadOnly))
            return QJsonObject();
        return QJsonDocument::fromJson(in.readAll()).object();
    };

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    const QString token = QStringLiteral("plan-export-token");
    backend.setApiKey(token);
    QVERIFY(backend.load(QUrl::fromLocalFile(rough)));
    QVERIFY(backend.planCut());
    QCOMPARE(backend.selects().size(), 7);
    QCOMPARE(backend.selects().at(2).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello"));
    QCOMPARE(backend.selects().at(2).toMap().value(QStringLiteral("keep")).toBool(), true);
    QCOMPARE(backend.selects().at(2).toMap().value(QStringLiteral("start")).toDouble(), 0.5);
    QCOMPARE(backend.selects().at(2).toMap().value(QStringLiteral("end")).toDouble(), 3.0);
    QCOMPARE(backend.selects().at(2).toMap().value(QStringLiteral("clip")).toInt(), 0);
    QCOMPARE(backend.cutClips(), (QStringList{fileA, fileB}));
    QCOMPARE(backend.m_plan.segments().size(), 2);
    QCOMPARE(backend.m_plan.segments().at(0).path, fileA);
    QCOMPARE(backend.m_plan.segments().at(0).start, 1.0);
    QCOMPARE(backend.m_plan.segments().at(0).end, 5.0);
    QCOMPARE(backend.m_plan.segments().at(1).path, fileB);
    QCOMPARE(backend.m_plan.segments().at(1).start, 0.5);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);
    QVERIFY(!backend.m_plan.unexported());
    QCOMPARE(backend.m_plan.duration(), 7.0);
    QCOMPARE(backend.m_plan.segments().at(0).text, QStringLiteral("hello"));
    QCOMPARE(backend.m_plan.segments().at(1).text, QString());
    const QVariantList shown = backend.m_plan.clipList();
    QCOMPARE(shown.size(), 2);
    QCOMPARE(shown.at(0).toMap().value(QStringLiteral("start")).toDouble(), 0.0);
    QCOMPARE(shown.at(0).toMap().value(QStringLiteral("end")).toDouble(), 4.0);
    QCOMPARE(shown.at(0).toMap().value(QStringLiteral("text")).toString(), QStringLiteral("hello"));
    QCOMPARE(shown.at(1).toMap().value(QStringLiteral("start")).toDouble(), 4.0);
    QCOMPARE(shown.at(1).toMap().value(QStringLiteral("end")).toDouble(), 7.0);
    QCOMPARE(shown.at(1).toMap().value(QStringLiteral("text")).toString(), QString());

    const QVariantMap at = backend.m_plan.sourceAt(0.5);
    QCOMPARE(at.value(QStringLiteral("ok")).toBool(), true);
    QCOMPARE(at.value(QStringLiteral("path")).toString(), fileA);
    QCOMPARE(at.value(QStringLiteral("source")).toDouble(), 1.5);

    // The blocks meet at 4s. That instant is the second source, not the tail of the first.
    const QVariantMap join = backend.m_plan.sourceAt(4.0);
    QCOMPARE(join.value(QStringLiteral("ok")).toBool(), true);
    QCOMPARE(join.value(QStringLiteral("path")).toString(), fileB);
    QCOMPARE(join.value(QStringLiteral("source")).toDouble(), 0.5);
    QCOMPARE(join.value(QStringLiteral("index")).toInt(), 1);
    QCOMPARE(join.value(QStringLiteral("clip")).toInt(), 2);
    QVERIFY(join.value(QStringLiteral("clip")).toInt() != join.value(QStringLiteral("index")).toInt());
    const QVariantMap joined = backend.m_plan.sourceFor(1, 0.5);
    QCOMPARE(joined.value(QStringLiteral("path")).toString(), fileB);
    QCOMPARE(joined.value(QStringLiteral("source")).toDouble(), 0.5);
    QCOMPARE(joined.value(QStringLiteral("index")).toInt(), 1);
    QCOMPARE(joined.value(QStringLiteral("clip")).toInt(), 2);
    // The true end of the last block still has a frame. There is no source after it.
    const QVariantMap tail = backend.m_plan.sourceAt(backend.m_plan.duration());
    QCOMPARE(tail.value(QStringLiteral("path")).toString(), fileB);
    QCOMPARE(tail.value(QStringLiteral("index")).toInt(), 1);
    QCOMPARE(tail.value(QStringLiteral("source")).toDouble(), 3.5);
    QCOMPARE(backend.m_plan.sourceFor(2, 0.5).value(QStringLiteral("ok")).toBool(), false);
    QCOMPARE(backend.m_plan.playableFrom(backend.m_plan.duration()), -1.0);

    // An in-point drag overlaps the previous block. The dragged segment is still B.
    backend.m_plan.beginGesture();
    QCOMPARE(backend.m_plan.duration(), 7.0);
    backend.m_plan.moveEdgeBy(1, true, -0.3);
    const double draggedStart = backend.m_plan.segments().at(1).start;
    QCOMPARE(draggedStart, 0.2);
    QCOMPARE(backend.m_plan.duration(), 7.0);
    const double overlapped = backend.m_plan.displayForSource(1, draggedStart);
    QVERIFY(overlapped < 4.0);
    QCOMPARE(backend.m_plan.sourceAt(overlapped).value(QStringLiteral("path")).toString(), fileA);
    const QVariantMap dragged = backend.m_plan.sourceFor(1, draggedStart);
    QCOMPARE(dragged.value(QStringLiteral("ok")).toBool(), true);
    QCOMPARE(dragged.value(QStringLiteral("path")).toString(), fileB);
    QCOMPARE(dragged.value(QStringLiteral("source")).toDouble(), draggedStart);
    QCOMPARE(dragged.value(QStringLiteral("index")).toInt(), 1);
    backend.m_plan.endGesture();
    const double packed = backend.m_plan.displayForSource(1, draggedStart);
    QCOMPARE(packed, 4.0);
    const QVariantMap packedHit = backend.m_plan.sourceAt(packed);
    QCOMPARE(packedHit.value(QStringLiteral("path")).toString(), fileB);
    QCOMPARE(packedHit.value(QStringLiteral("source")).toDouble(), draggedStart);
    backend.m_plan.undo();
    QCOMPARE(backend.m_plan.segments().at(0).start, 1.0);
    QCOMPARE(backend.m_plan.segments().at(0).end, 5.0);
    QCOMPARE(backend.m_plan.segments().at(1).start, 0.5);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);
    QCOMPARE(backend.m_plan.duration(), 7.0);
    QVERIFY(!backend.m_plan.unexported());

    const edit::Clips baked = backend.timeline()->clips();
    backend.m_plan.moveEdge(0, false, 2.5);
    QCOMPARE(backend.timeline()->clips(), baked);
    QCOMPARE(backend.m_plan.segments().at(0).start, 1.0);
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.5);
    QCOMPARE(backend.m_plan.segments().at(1).start, 0.5);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);
    QCOMPARE(backend.m_plan.segments().at(1).reason, QStringLiteral("wide"));
    QVERIFY(backend.m_plan.unexported());
    QCOMPARE(backend.m_plan.duration(), 5.5);

    const QVariantMap next = backend.m_plan.sourceAt(2.75);
    QCOMPARE(next.value(QStringLiteral("path")).toString(), fileB);
    QCOMPARE(next.value(QStringLiteral("source")).toDouble(), 0.75);
    const QVariantMap shortenedJoin = backend.m_plan.sourceAt(2.5);
    QCOMPARE(shortenedJoin.value(QStringLiteral("path")).toString(), fileB);
    QCOMPARE(shortenedJoin.value(QStringLiteral("source")).toDouble(), 0.5);
    QCOMPARE(shortenedJoin.value(QStringLiteral("index")).toInt(), 1);
    // Releasing this out-point keeps the picture on the trimmed segment.
    // Playback at the shared boundary still loads the next source.
    const double outEdge = backend.m_plan.segments().at(0).end;
    QCOMPARE(outEdge, 3.5);
    const double boundary = backend.m_plan.displayForSource(0, outEdge);
    QCOMPARE(boundary, 2.5);
    QCOMPARE(backend.m_plan.sourceAt(boundary).value(QStringLiteral("path")).toString(), fileB);
    const QVariantMap releasePicture = backend.m_plan.sourceFor(0, outEdge);
    QCOMPARE(releasePicture.value(QStringLiteral("ok")).toBool(), true);
    QCOMPARE(releasePicture.value(QStringLiteral("path")).toString(), fileA);
    QCOMPARE(releasePicture.value(QStringLiteral("source")).toDouble(), outEdge);
    QCOMPARE(releasePicture.value(QStringLiteral("index")).toInt(), 0);
    const double parked = backend.m_plan.playheadForEdge(0, false);
    QVERIFY(parked < boundary);
    QVERIFY(parked > backend.m_plan.displayForSource(0, backend.m_plan.segments().at(0).start));
    const QVariantMap parkedHit = backend.m_plan.sourceAt(parked);
    QCOMPARE(parkedHit.value(QStringLiteral("path")).toString(), fileA);
    QCOMPARE(parkedHit.value(QStringLiteral("index")).toInt(), 0);
    QVERIFY(qFuzzyIsNull(backend.m_plan.playheadForEdge(0, true)));
    QCOMPARE(backend.m_plan.sourceAt(backend.m_plan.playheadForEdge(0, true)).value(QStringLiteral("path")).toString(),
             fileA);

    const QJsonArray shortened = readRoot().value(QStringLiteral("segments")).toArray();
    QCOMPARE(shortened.size(), 2);
    QCOMPARE(shortened.at(0).toObject().value(QStringLiteral("start")).toDouble(), 1.0);
    QCOMPARE(shortened.at(0).toObject().value(QStringLiteral("end")).toDouble(), 3.5);
    QCOMPARE(shortened.at(0).toObject().value(QStringLiteral("reason")).toString(), QStringLiteral("story"));
    QCOMPARE(shortened.at(0).toObject().value(QStringLiteral("note")).toString(), QStringLiteral("keep"));
    QCOMPARE(shortened.at(1).toObject().value(QStringLiteral("start")).toDouble(), 0.5);
    QCOMPARE(shortened.at(1).toObject().value(QStringLiteral("end")).toDouble(), 3.5);
    QCOMPARE(shortened.at(1).toObject().value(QStringLiteral("reason")).toString(), QStringLiteral("wide"));
    QVERIFY(!shortened.at(0).toObject().contains(QStringLiteral("text")));
    QVERIFY(!shortened.at(1).toObject().contains(QStringLiteral("text")));
    QCOMPARE(readRoot().value(QStringLiteral("trimmed")).toBool(), true);
    backend.writeCaptions();
    backend.makeShort();
    QCOMPARE(backend.status(), QStringLiteral("Export the trim first"));
    QVERIFY(!backend.busy());
    QVERIFY(backend.m_cutProcess == nullptr);
    QCOMPARE(readRoot().value(QStringLiteral("trimmed")).toBool(), true);
    QCOMPARE(readRoot().value(QStringLiteral("intent")).toString(), QStringLiteral("A quiet ride"));
    QCOMPARE(readRoot().value(QStringLiteral("lines")).toArray().at(2).toObject().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello"));
    QCOMPARE(readRoot().value(QStringLiteral("clips")).toArray().at(1).toObject().value(QStringLiteral("path")).toString(),
             fileB);

    backend.m_plan.moveEdge(0, false, 100.0);
    QCOMPARE(backend.m_plan.segments().at(0).end, 8.0);
    QCOMPARE(backend.m_plan.segments().at(0).start, 1.0);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);
    backend.m_plan.moveEdge(0, false, 0.0);
    const double shortLen = backend.m_plan.segments().at(0).end - backend.m_plan.segments().at(0).start;
    QVERIFY(shortLen + 1e-9 >= edit::minimumClip);
    QVERIFY(shortLen < 0.15);
    QCOMPARE(backend.m_plan.segments().at(1).start, 0.5);
    backend.m_plan.moveEdge(0, false, 2.5);
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.5);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);

    backend.m_plan.beginGesture();
    backend.m_plan.moveEdge(0, false, 1.5);
    backend.m_plan.moveEdge(0, false, 2.0);
    backend.m_plan.endGesture();
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.0);
    backend.m_plan.undo();
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.5);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);
    backend.m_plan.redo();
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.0);
    backend.m_plan.undo();
    QCOMPARE(backend.m_plan.segments().at(0).start, 1.0);
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.5);

    backend.m_plan.removeClip(0);
    QCOMPARE(backend.m_plan.segments().size(), 1);
    QCOMPARE(backend.m_plan.segments().at(0).path, fileB);
    backend.m_plan.restoreGap(0);
    QCOMPARE(backend.m_plan.segments().size(), 2);
    QCOMPARE(backend.m_plan.segments().at(0).text, QStringLiteral("hello"));
    QCOMPARE(backend.m_plan.clipList().at(0).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello"));
    QCOMPARE(backend.m_plan.segments().at(0).start, 1.0);
    QCOMPARE(backend.m_plan.segments().at(0).end, 5.0);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);
    backend.m_plan.undo();
    QCOMPARE(backend.m_plan.segments().size(), 1);
    backend.m_plan.undo();
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.5);
    QCOMPARE(backend.m_plan.segments().at(0).start, 1.0);
    QCOMPARE(backend.m_plan.segments().at(1).start, 0.5);
    QCOMPARE(backend.m_plan.segments().at(1).end, 3.5);
    QVERIFY(backend.m_plan.unexported());

    const QString stub = m_dir.filePath(QStringLiteral("render-stub.sh"));
    {
        QFile script(stub);
        QVERIFY(script.open(QIODevice::WriteOnly | QIODevice::Truncate));
        QVERIFY(script.write("#!/bin/sh\nexit 0\n") > 0);
    }
    QVERIFY(QFile::setPermissions(stub, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));
    backend.m_launchProgram = stub;
    backend.exportPlan();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QVERIFY(backend.m_cutProcess);
    const QStringList args = backend.m_cutProcess->arguments();
    QVERIFY(args.contains(QStringLiteral("render")));
    QVERIFY(args.contains(QFileInfo(cutsPath).absolutePath()));
    QCOMPARE(args.at(args.indexOf(QStringLiteral("--b-roll-sound")) + 1), QStringLiteral("mix"));
    QVERIFY(!args.join(QLatin1Char(' ')).contains(token));
    // A finished export matches the file, so Export waits for the next trim.
    QVERIFY(!backend.m_plan.unexported());
    backend.m_plan.moveEdge(0, false, 2.0);
    QVERIFY(backend.m_plan.unexported());
    backend.setBrollMix(false);
    backend.exportPlan();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    const QStringList voiceArgs = backend.m_cutProcess->arguments();
    QVERIFY(voiceArgs.contains(QStringLiteral("render")));
    QCOMPARE(voiceArgs.at(voiceArgs.indexOf(QStringLiteral("--b-roll-sound")) + 1), QStringLiteral("voice"));
    QVERIFY(!voiceArgs.join(QLatin1Char(' ')).contains(token));
    backend.setBrollMix(true);
    // The checks below still read the 3.5 out point.
    backend.m_plan.moveEdge(0, false, 2.5);
    QCOMPARE(backend.m_plan.segments().at(0).end, 3.5);
    QVERIFY(backend.writePlanSegments());
    QVERIFY(!args.contains(QStringLiteral("XAI_API_KEY")));
    QCOMPARE(backend.m_cutProcess->processEnvironment().value(QStringLiteral("BOTCUT_FAKE")),
             QStringLiteral("1"));
    QCOMPARE(backend.m_cutProcess->processEnvironment().value(QStringLiteral("XAI_API_KEY")), token);
    QVERIFY(!backend.status().contains(token));

    const QJsonObject exported = readRoot();
    const QJsonArray exportedSegs = exported.value(QStringLiteral("segments")).toArray();
    QCOMPARE(exportedSegs.at(0).toObject().value(QStringLiteral("end")).toDouble(), 3.5);
    QCOMPARE(exportedSegs.at(0).toObject().value(QStringLiteral("start")).toDouble(), 1.0);
    QCOMPARE(exportedSegs.at(1).toObject().value(QStringLiteral("start")).toDouble(), 0.5);
    QCOMPARE(exportedSegs.at(1).toObject().value(QStringLiteral("end")).toDouble(), 3.5);
    QCOMPARE(exportedSegs.at(1).toObject().value(QStringLiteral("reason")).toString(), QStringLiteral("wide"));
    QVERIFY(!exportedSegs.at(0).toObject().contains(QStringLiteral("text")));
    QVERIFY(!exportedSegs.at(1).toObject().contains(QStringLiteral("text")));
    QCOMPARE(exported.value(QStringLiteral("trimmed")).toBool(), true);
    QVERIFY(!QString::fromUtf8(QJsonDocument(exported).toJson()).contains(token));

    QVERIFY(backend.writeSelects(cutsPath));
    const QJsonObject cleared = readRoot();
    QVERIFY(!cleared.contains(QStringLiteral("trimmed")));
    QCOMPARE(cleared.value(QStringLiteral("segments")).toArray().at(0).toObject().value(QStringLiteral("end")).toDouble(),
             3.5);

    QFile beforePlain(cutsPath);
    QVERIFY(beforePlain.open(QIODevice::ReadOnly));
    const QByteArray plainSnapshot = beforePlain.readAll();
    beforePlain.close();

    const QString plain = makeVideo(QStringLiteral("plain-after-plan.mp4"), 4.0, false);
    QVERIFY(!plain.isEmpty());
    QVERIFY(backend.load(QUrl::fromLocalFile(plain)));
    QVERIFY(!backend.planCut());
    QVERIFY(backend.selects().isEmpty());
    QVERIFY(backend.cutClips().isEmpty());
    QCOMPARE(backend.timeline()->clips().size(), 1);
    QVERIFY(qFuzzyIsNull(backend.timeline()->clips().at(0).start));
    QVERIFY(backend.timeline()->clips().at(0).end > 3.0);
    backend.timeline()->moveEdge(0, false, 2.0);
    QCOMPARE(backend.timeline()->clips().size(), 1);
    QVERIFY(qFuzzyIsNull(backend.timeline()->clips().at(0).start));
    QCOMPARE(backend.timeline()->clips().at(0).end, 2.0);
    QVERIFY(!backend.planCut());
    QFile afterPlain(cutsPath);
    QVERIFY(afterPlain.open(QIODevice::ReadOnly));
    QCOMPARE(afterPlain.readAll(), plainSnapshot);
    QDir(dirPath).removeRecursively();
}

void BackendTests::savedCutKeepsTheLineList() {
    const QString fileA = makeVideo(QStringLiteral("saved-line-a.mp4"), 4.0, false);
    QVERIFY(!fileA.isEmpty());
    const QString dirPath = QDir::temp().filePath(QStringLiteral("botcut-cut-save-lines"));
    QDir(dirPath).removeRecursively();
    QVERIFY(QDir().mkpath(dirPath));
    const QString rough = QDir(dirPath).filePath(QStringLiteral("rough_cut.mp4"));
    QVERIFY(QFile::copy(fileA, rough));
    const QString saved = m_dir.filePath(QStringLiteral("saved-ride.mp4"));
    QFile::remove(saved);
    QVERIFY(QFile::copy(fileA, saved));

    QJsonObject clip;
    clip.insert(QStringLiteral("index"), 0);
    clip.insert(QStringLiteral("path"), fileA);
    clip.insert(QStringLiteral("duration"), 4.0);
    QJsonObject segment;
    segment.insert(QStringLiteral("clip"), 0);
    segment.insert(QStringLiteral("start"), 1.0);
    segment.insert(QStringLiteral("end"), 3.0);
    QJsonObject line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("clip"), 0);
    line.insert(QStringLiteral("start"), 1.0);
    line.insert(QStringLiteral("end"), 2.5);
    line.insert(QStringLiteral("text"), QStringLiteral("hello"));
    line.insert(QStringLiteral("keep"), true);
    QJsonObject root;
    root.insert(QStringLiteral("clips"), QJsonArray{clip});
    root.insert(QStringLiteral("segments"), QJsonArray{segment});
    root.insert(QStringLiteral("lines"), QJsonArray{line});
    const QString cutsPath = QDir(dirPath).filePath(QStringLiteral("cuts.json"));
    {
        QFile file(cutsPath);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Indented);
        QCOMPARE(file.write(bytes), bytes.size());
    }

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVERIFY(backend.load(QUrl::fromLocalFile(rough)));
    QVERIFY(backend.planCut());
    QCOMPARE(backend.selects().size(), 1);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello"));
    QCOMPARE(backend.cutClips(), (QStringList{fileA}));

    // A new name is not rough_cut.mp4, and the cuts path is not remembered yet.
    backend.finishSavedCut(saved);
    QCOMPARE(backend.source(), QUrl::fromLocalFile(QFileInfo(saved).absoluteFilePath()));
    QVERIFY(backend.planCut());
    QCOMPARE(backend.selects().size(), 1);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("text")).toString(),
             QStringLiteral("hello"));
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool(), true);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("start")).toDouble(), 1.0);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("end")).toDouble(), 2.5);
    QCOMPARE(backend.selects().at(0).toMap().value(QStringLiteral("clip")).toInt(), 0);
    QCOMPARE(backend.cutClips(), (QStringList{fileA}));
    waitForBackgroundWork(backend);
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
    const QString key = QStringLiteral("accent");

    // No file at all — the non-omarchy case — keeps the fallback.
    QCOMPARE(Theme::readColor(m_dir.filePath(QStringLiteral("missing.toml")), key, fallback), fallback);

    const auto writeColors = [&colorsPath](const char *contents) {
        QFile file(colorsPath);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        file.write(contents);
    };

    writeColors("# omarchy theme\n"
                "mode = \"dark\"\n"
                "background = \"#121212\"\n"
                "accent = \"#33ccff\"\n");
    QCOMPARE(Theme::readColor(colorsPath, key, fallback), QStringLiteral("#33ccff"));

    writeColors("accent = '#aabbcc'\n");
    QCOMPARE(Theme::readColor(colorsPath, key, fallback), QStringLiteral("#aabbcc"));

    // A value that isn't a color keeps the fallback rather than breaking bindings.
    writeColors("accent = \"not-a-color\"\n");
    QCOMPARE(Theme::readColor(colorsPath, key, fallback), fallback);

    // As does a theme without an accent at all.
    writeColors("background = \"#121212\"\n");
    QCOMPARE(Theme::readColor(colorsPath, key, fallback), fallback);
}

static QString accentForegroundFromFile(const QByteArray &colorsToml) {
    QTemporaryDir dir;
    if (!dir.isValid())
        return {};
    QDir(dir.path()).mkpath(QStringLiteral("theme"));
    QFile colors(dir.filePath(QStringLiteral("theme/colors.toml")));
    if (!colors.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return {};
    colors.write(colorsToml);
    colors.close();
    Theme theme(dir.path(), nullptr, QString());
    return theme.accentForeground();
}

void BackendTests::themeAccentForegroundKeepsContrast() {
    QCOMPARE(accentForegroundFromFile("accent = \"#FFD60A\"\n"), QStringLiteral("black"));
    QCOMPARE(accentForegroundFromFile("accent = \"#222266\"\n"), QStringLiteral("white"));
    // An unparsable accent falls back to #FFD60A, so the contrast stays black.
    QCOMPARE(accentForegroundFromFile("accent = \"garbage\"\n"), QStringLiteral("black"));
}

void BackendTests::themeReadsAccentForegroundAndRounding() {
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    QCOMPARE(Theme::readColor(dir.filePath(QStringLiteral("missing.toml")), QStringLiteral("accent"),
                              QStringLiteral("#FFD60A")),
             QStringLiteral("#FFD60A"));
    QDir(dir.path()).mkpath(QStringLiteral("theme"));
    QFile colors(dir.filePath(QStringLiteral("theme/colors.toml")));
    QVERIFY(colors.open(QIODevice::WriteOnly));
    colors.write("accent = \"#112233\"\nforeground = \"#abcdef\"\nbackground = \"#010203\"\n");
    colors.close();

    Theme theme(dir.path(), nullptr, QString());
    QCOMPARE(theme.accent(), QStringLiteral("#112233"));
    QCOMPARE(theme.accentForeground(), QStringLiteral("white"));
    QCOMPARE(theme.foreground(), QStringLiteral("#abcdef"));
    QCOMPARE(theme.background(), QStringLiteral("#010203"));
    QCOMPARE(theme.radius(), 0);

    QTemporaryDir defaultsDir;
    QVERIFY(defaultsDir.isValid());
    QDir(defaultsDir.path()).mkpath(QStringLiteral("theme"));
    QFile defaults(defaultsDir.filePath(QStringLiteral("theme/colors.toml")));
    QVERIFY(defaults.open(QIODevice::WriteOnly));
    defaults.write("background = \"#0e0e10\"\nforeground = \"#f4f4f5\"\naccent = \"#FFD60A\"\n");
    defaults.close();
    Theme painted(defaultsDir.path(), nullptr, QString());
    QCOMPARE(painted.background(), QStringLiteral("#0e0e10"));
    QCOMPARE(painted.foreground(), QStringLiteral("#f4f4f5"));
    const auto hex6 = [](const QString &value) {
        if (value.size() != 7 || value.at(0) != QLatin1Char('#'))
            return false;
        for (int i = 1; i < value.size(); ++i) {
            const QChar c = value.at(i);
            const bool digit = c.isDigit();
            const bool lower = c >= QLatin1Char('a') && c <= QLatin1Char('f');
            const bool upper = c >= QLatin1Char('A') && c <= QLatin1Char('F');
            if (!digit && !lower && !upper)
                return false;
        }
        return true;
    };
    QVERIFY(hex6(painted.surface()));
    QVERIFY(hex6(painted.raised()));
    QVERIFY(hex6(painted.selected()));
    QVERIFY(hex6(painted.hover()));
    QVERIFY(hex6(painted.line()));
    QVERIFY(painted.surface() != painted.background());
}

void BackendTests::stepFollowsTheTrayAndTheLines() {
    EnvVarGuard keyGuard("XAI_API_KEY");
    qunsetenv("XAI_API_KEY");

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QCOMPARE(backend.step(), QStringLiteral("empty"));

    const QString shot = m_dir.filePath(QStringLiteral("step-shot.mp4"));
    QVERIFY(QFile(shot).open(QIODevice::WriteOnly));
    backend.addTrayFiles({shot});
    QCOMPARE(backend.step(), QStringLiteral("needsKey"));

    backend.setCutMode(QStringLiteral("assemble"));
    QCOMPARE(backend.step(), QStringLiteral("shotsReady"));

    const QString missing = m_dir.filePath(QStringLiteral("step-gone.mp4"));
    QFile missingList(m_dir.filePath(QStringLiteral("step-missing.botcut.json")));
    QVERIFY(missingList.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray missingBytes = writeCutList(QStringLiteral("assemble"), {missing});
    QCOMPARE(missingList.write(missingBytes), missingBytes.size());
    missingList.close();
    backend.addDropped({QUrl::fromLocalFile(missingList.fileName())});
    QCOMPARE(backend.step(), QStringLiteral("missingShot"));

    QVariantMap kept;
    kept.insert(QStringLiteral("id"), 1);
    kept.insert(QStringLiteral("keep"), true);
    kept.insert(QStringLiteral("text"), QStringLiteral("hello"));
    const QString listed = m_dir.filePath(QStringLiteral("step-listed.mp4"));
    QVERIFY(QFile(listed).open(QIODevice::WriteOnly));
    QFile list(m_dir.filePath(QStringLiteral("step.botcut.json")));
    QVERIFY(list.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray bytes = writeCutList(QStringLiteral("speech"), {listed}, QString(), {kept});
    QCOMPARE(list.write(bytes), bytes.size());
    list.close();
    backend.addDropped({QUrl::fromLocalFile(list.fileName())});
    QCOMPARE(backend.step(), QStringLiteral("lines"));
    backend.dropSelect(1);
    QCOMPARE(backend.step(), QStringLiteral("allDropped"));
    backend.restoreSelect(1);
    QCOMPARE(backend.step(), QStringLiteral("lines"));
}

void BackendTests::jobFollowsTheStatusLine() {
    QString job;
    qreal progress = 0;
    QString text;
    QVERIFY(Backend::describeJob(QStringLiteral("Rendering 42%"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("rendering"));
    QCOMPARE(progress, 0.42);
    QCOMPARE(text, QStringLiteral("Rendering 42%"));

    QVERIFY(Backend::describeJob(QStringLiteral("Exporting 30%"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("exporting"));
    QCOMPARE(progress, 0.30);
    QCOMPARE(text, QStringLiteral("Exporting 30%"));

    QVERIFY(Backend::describeJob(QStringLiteral("Opening 7%"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("opening"));
    QCOMPARE(progress, 0.07);

    QVERIFY(Backend::describeJob(QStringLiteral("Transcribing 2/4 room.mp4"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("transcribing"));
    QCOMPARE(progress, 0.5);
    QCOMPARE(text, QStringLiteral("Transcribing 2 of 4"));

    QVERIFY(Backend::describeJob(QStringLiteral("Reading files"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("reading"));
    QCOMPARE(text, QStringLiteral("Reading shots"));
    QVERIFY(Backend::describeJob(QStringLiteral("Choosing takes"), &job, &progress, &text));
    QCOMPARE(text, QStringLiteral("Choosing lines"));
    QVERIFY(Backend::describeJob(QStringLiteral("Changing…"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("changing"));
    QCOMPARE(text, QStringLiteral("Changing the list"));
    QVERIFY(qAbs(progress) < 0.0001);
    // The CLI can still print the old word. The bar must not go blank.
    QVERIFY(Backend::describeJob(QStringLiteral("Revising"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("changing"));
    QCOMPARE(text, QStringLiteral("Changing the list"));
    QVERIFY(Backend::describeJob(QStringLiteral("Making the card…"), &job, &progress, &text));
    QCOMPARE(text, QStringLiteral("Making the title card"));
    QVERIFY(Backend::describeJob(QStringLiteral("Saving…"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("saving"));
    QVERIFY(qAbs(progress) < 0.0001);
    QVERIFY(Backend::describeJob(QStringLiteral("Opening…"), &job, &progress, &text));
    QCOMPARE(job, QStringLiteral("opening"));
    QCOMPARE(text, QStringLiteral("Opening…"));
    QVERIFY(qAbs(progress) < 0.0001);

    QVERIFY(!Backend::describeJob(QStringLiteral("Trying again"), &job, &progress, &text));
    QVERIFY(Backend::describeJob(QStringLiteral("Saved the list"), &job, &progress, &text));
    QCOMPARE(job, QString());
    QVERIFY(qAbs(progress + 1.0) < 0.0001);
}

static QString showAndGrab(QQuickWindow *window, const QString &path) {
    if (!window)
        return QStringLiteral("no window for ") + path;
    window->resize(960, 640);
    window->show();
    // Offscreen sometimes never reports exposed. The grab is the check that matters.
    if (!QTest::qWaitForWindowExposed(window, 2000))
        window->requestUpdate();
    window->requestUpdate();
    QCoreApplication::processEvents();
    QTest::qWait(80);
    const QImage image = window->grabWindow();
    if (image.size() != QSize(960, 640)) {
        return QStringLiteral("size %1x%2 for %3")
            .arg(image.width())
            .arg(image.height())
            .arg(path);
    }
    if (!image.save(path))
        return QStringLiteral("save failed: ") + path;
    return {};
}

class GrabSession {
public:
    GrabSession(Theme *theme, ShortcutBackend *backend) {
        m_engine.addImageProvider(QStringLiteral("thumbs"), new ThumbProvider);
        m_engine.rootContext()->setContextProperty(QStringLiteral("theme"), theme);
        m_engine.rootContext()->setContextProperty(QStringLiteral("backend"), backend);
        m_engine.load(QUrl::fromLocalFile(mainQmlPath()));
        if (!m_engine.rootObjects().isEmpty())
            m_window = qobject_cast<QQuickWindow *>(m_engine.rootObjects().first());
    }

    QQuickWindow *window() const { return m_window; }
    QString grab(const QString &path) { return showAndGrab(m_window, path); }

private:
    QQmlApplicationEngine m_engine;
    QQuickWindow *m_window = nullptr;
};

void BackendTests::grabWindowScreens() {
    if (!qEnvironmentVariableIsSet("BOTCUT_GRABS"))
        return;

    const QString outDir = QFileInfo(QString::fromUtf8(__FILE__)).dir()
                               .absoluteFilePath(QStringLiteral("../docs/screenshots"));
    QVERIFY(QDir().mkpath(outDir));

    const QString hyprctl = m_dir.filePath(QStringLiteral("grab-hyprctl"));
    QFile script(hyprctl);
    QVERIFY(script.open(QIODevice::WriteOnly | QIODevice::Truncate));
    const QByteArray body = QByteArrayLiteral("#!/bin/sh\nprintf '%s\\n' '{\"int\": 8}'\n");
    QCOMPARE(script.write(body), static_cast<qint64>(body.size()));
    script.close();
    QVERIFY(script.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));

    const QString tags[] = {QStringLiteral("r0"), QStringLiteral("r8")};
    const QString hyprs[] = {QString(), hyprctl};
    for (int pass = 0; pass < 2; ++pass) {
        Theme theme(m_dir.filePath(QStringLiteral("grab-theme-%1").arg(tags[pass])), nullptr, hyprs[pass]);
        if (hyprs[pass].isEmpty()) {
            QCOMPARE(theme.radius(), 0);
        } else {
            QSignalSpy changed(&theme, &Theme::changed);
            bool arrived = theme.radius() == 8;
            while (!arrived) {
                if (!changed.wait(4000))
                    break;
                arrived = theme.radius() == 8;
                changed.clear();
            }
            QVERIFY2(arrived, "Theme::changed never brought radius 8");
        }

        const QString tag = tags[pass];
        const auto png = [&outDir, &tag](const char *name) {
            return outDir + QLatin1Char('/') + QLatin1String(name) + QLatin1Char('-') + tag
                + QStringLiteral(".png");
        };

        {
            ShortcutBackend backend(QUrl(), 0.0);
            GrabSession session(&theme, &backend);
            QVERIFY(session.window());
            QVERIFY(session.window()->findChild<QQuickItem *>(QStringLiteral("settingsButton")));
            QVERIFY(session.window()->findChild<QQuickItem *>(QStringLiteral("cutButton")));
            QCOMPARE(session.grab(png("empty")), QString());

            QVERIFY(session.window()->setProperty("settingsOpen", true));
            QCOMPARE(session.grab(png("settings")), QString());
            QVERIFY(session.window()->findChild<QQuickItem *>(QStringLiteral("spokenCutsBox")));
            QVERIFY(session.window()->setProperty("settingsOpen", false));

            QVERIFY(session.window()->setProperty("helpVisible", true));
            QCOMPARE(session.grab(png("help")), QString());
            QVERIFY(session.window()->setProperty("helpVisible", false));

            QVERIFY(session.window()->setProperty("titleCardOpen", true));
            QCOMPARE(session.grab(png("title")), QString());
            QVERIFY(session.window()->setProperty("titleCardOpen", false));

            QVERIFY(session.window()->setProperty("quitConfirmVisible", true));
            QCOMPARE(session.grab(png("quit")), QString());
            QVERIFY(session.window()->setProperty("quitConfirmVisible", false));
        }
        {
            ShortcutBackend backend(QUrl(), 0.0);
            backend.setTray({m_dir.filePath(QStringLiteral("DJI_20261008_091204.MP4"))});
            backend.setCutMode(QStringLiteral("assemble"));
            GrabSession session(&theme, &backend);
            QVERIFY(session.window());
            QCOMPARE(session.grab(png("shots")), QString());
        }
        {
            ShortcutBackend backend(QUrl(), 0.0);
            QVariantMap kept;
            kept.insert(QStringLiteral("id"), 1);
            kept.insert(QStringLiteral("keep"), true);
            kept.insert(QStringLiteral("text"), QStringLiteral("We started in the garage."));
            kept.insert(QStringLiteral("start"), 12.0);
            kept.insert(QStringLiteral("end"), 18.0);
            kept.insert(QStringLiteral("clip"), 0);
            QVariantMap dropped;
            dropped.insert(QStringLiteral("id"), 2);
            dropped.insert(QStringLiteral("keep"), false);
            dropped.insert(QStringLiteral("text"),
                           QStringLiteral("The first customers were shops on the same street."));
            dropped.insert(QStringLiteral("start"), 41.0);
            dropped.insert(QStringLiteral("end"), 48.0);
            dropped.insert(QStringLiteral("clip"), 0);
            dropped.insert(QStringLiteral("reason"), QStringLiteral("dropped"));
            backend.setSelects({kept, dropped});
            backend.setTray({m_dir.filePath(QStringLiteral("DJI_20261008_091204.MP4"))});
            backend.setChat({ShortcutBackend::turn(QStringLiteral("you"), QStringLiteral("drop the pricing part")),
                             ShortcutBackend::turn(QStringLiteral("bot"),
                                                   QStringLiteral("I'd drop the line about the first customers and keep the garage."),
                                                   QStringLiteral("Drops 1 line."))},
                            true);
            GrabSession session(&theme, &backend);
            QVERIFY(session.window());
            QVERIFY(session.window()->setProperty("currentLine", 0));
            QCOMPARE(session.grab(png("lines")), QString());

            QVERIFY(session.window()->setProperty("confirmCutOpen", true));
            QCOMPARE(session.grab(png("confirm")), QString());
            QVERIFY(session.window()->setProperty("confirmCutOpen", false));
        }
        {
            ShortcutBackend backend(QUrl::fromLocalFile(m_videoPath), 1.0);
            GrabSession session(&theme, &backend);
            QVERIFY(session.window());
            QQuickItem *editBar = session.window()->findChild<QQuickItem *>(QStringLiteral("editBar"));
            QVERIFY(editBar);
            QCOMPARE(session.grab(png("movie")), QString());
            QVERIFY2(editBar->isVisible(), "edit bar hidden on the movie screen");
        }
    }
}

namespace {
QString writeStubScript(const QString &path, const QByteArray &body) {
    QFile script(path);
    if (!script.open(QIODevice::WriteOnly | QIODevice::Truncate) || script.write(body) <= 0)
        return {};
    script.close();
    QFile::setPermissions(path, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner);
    return path;
}

// A cut folder with one line in cuts.json, ready for Render.
QString writeOneLineCut(const QString &dir, bool keep) {
    QDir().mkpath(dir);
    QJsonObject line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), keep);
    QJsonObject root;
    root.insert(QStringLiteral("lines"), QJsonArray{line});
    const QString cuts = QDir(dir).filePath(QStringLiteral("cuts.json"));
    QFile file(cuts);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return {};
    file.write(QJsonDocument(root).toJson(QJsonDocument::Indented));
    return cuts;
}
}

void BackendTests::failedJobLeavesItsReasonOnScreen() {
    const QString stub = writeStubScript(m_dir.filePath(QStringLiteral("fail-stub.sh")),
                                         "#!/bin/sh\necho 'Rendering 10%'\necho 'xAI connection failed' >&2\nexit 1\n");
    QVERIFY(!stub.isEmpty());
    const QString dir = m_dir.filePath(QStringLiteral("fail-cut"));
    QVERIFY(!writeOneLineCut(dir, true).isEmpty());

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    backend.m_selects = {line};
    backend.m_cutOut = dir;
    backend.m_launchProgram = stub;
    QSignalSpy noticeSpy(&backend, &Backend::notice);

    backend.renderSelects();
    QVERIFY(backend.busy());
    QVERIFY(backend.lastError().isEmpty());
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    // The tool's last line is the reason, and it stays after the job is gone.
    QCOMPARE(backend.lastError(), QStringLiteral("xAI connection failed"));
    QCOMPARE(backend.job(), QString());
    QCOMPARE(noticeSpy.count(), 0);

    // Trying again clears it while the job runs, and the same failure says so again.
    backend.renderSelects();
    QVERIFY(backend.lastError().isEmpty());
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QCOMPARE(backend.lastError(), QStringLiteral("xAI connection failed"));

    backend.dismissError();
    QVERIFY(backend.lastError().isEmpty());

    // Good news is a passing notice, never an error.
    backend.setStatus(QStringLiteral("Wrote the captions"));
    QVERIFY(backend.lastError().isEmpty());
    QCOMPARE(noticeSpy.count(), 1);
    QCOMPARE(noticeSpy.at(0).at(0).toString(), QStringLiteral("Wrote the captions"));
}

void BackendTests::stopEndsTheJobAndItsChildrenQuietly() {
    const QString pidFile = m_dir.filePath(QStringLiteral("stop-child.pid"));
    QFile::remove(pidFile);
    const QByteArray body = "#!/bin/sh\necho 'Rendering 5%'\nsleep 60 &\necho $! > '" + pidFile.toUtf8()
                            + "'\nwait\n";
    const QString stub = writeStubScript(m_dir.filePath(QStringLiteral("stop-stub.sh")), body);
    QVERIFY(!stub.isEmpty());
    const QString dir = m_dir.filePath(QStringLiteral("stop-cut"));
    QVERIFY(!writeOneLineCut(dir, true).isEmpty());

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), true);
    backend.m_selects = {line};
    backend.m_cutOut = dir;
    backend.m_launchProgram = stub;

    // Nothing running: Stop does nothing.
    backend.cancelJob();
    QVERIFY(!backend.busy());

    backend.renderSelects();
    QVERIFY(backend.busy());
    QTRY_VERIFY_WITH_TIMEOUT(QFileInfo(pidFile).size() > 0, 5000);
    QFile pids(pidFile);
    QVERIFY(pids.open(QIODevice::ReadOnly));
    const pid_t child = pid_t(pids.readAll().trimmed().toLongLong());
    QVERIFY(child > 0);
    QCOMPARE(::kill(child, 0), 0);

    backend.cancelJob();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    // Stop is not a failure, and the lines are still there to render.
    QCOMPARE(backend.lastError(), QString());
    QCOMPARE(backend.status(), QString());
    QCOMPARE(backend.job(), QString());
    QCOMPARE(backend.selects().size(), 1);
    QCOMPARE(backend.step(), QStringLiteral("empty"));
    // The sleep the script started is gone too, not left running behind the window.
    QTRY_VERIFY_WITH_TIMEOUT(::kill(child, 0) != 0, 5000);
}

void BackendTests::restoreSelectSavesTheList() {
    const QString dir = m_dir.filePath(QStringLiteral("restore-cut"));
    const QString cuts = writeOneLineCut(dir, false);
    QVERIFY(!cuts.isEmpty());
    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    QVariantMap line;
    line.insert(QStringLiteral("id"), 1);
    line.insert(QStringLiteral("keep"), false);
    backend.m_selects = {line};
    backend.m_cutOut = dir;

    backend.restoreSelect(1);
    QVERIFY(backend.selects().at(0).toMap().value(QStringLiteral("keep")).toBool());
    QFile file(cuts);
    QVERIFY(file.open(QIODevice::ReadOnly));
    const QJsonArray lines = QJsonDocument::fromJson(file.readAll()).object().value(QStringLiteral("lines")).toArray();
    QCOMPARE(lines.size(), 1);
    // The file follows the list at once, as it does for a drop.
    QCOMPARE(lines.at(0).toObject().value(QStringLiteral("keep")).toBool(), true);
}

void BackendTests::captionsLandBesideTheSavedMovie() {
    // The tool writes rough_cut.srt beside cuts.json. The movie was saved somewhere else.
    const QString stub = writeStubScript(
        m_dir.filePath(QStringLiteral("captions-stub.sh")),
        "#!/bin/sh\nprintf '1\\n00:00:00,000 --> 00:00:01,000\\nhello\\n' > \"$(dirname \"$2\")/rough_cut.srt\"\nexit 0\n");
    QVERIFY(!stub.isEmpty());
    const QString dir = m_dir.filePath(QStringLiteral("captions-cut"));
    const QString cuts = writeOneLineCut(dir, true);
    QVERIFY(!cuts.isEmpty());
    const QString savedDir = m_dir.filePath(QStringLiteral("captions-saved"));
    QVERIFY(QDir().mkpath(savedDir));
    const QString movie = QDir(savedDir).filePath(QStringLiteral("ride.mp4"));
    QVERIFY(QFile(movie).open(QIODevice::WriteOnly));

    ThumbProvider provider;
    Backend backend(&provider, new FakeFilePicker);
    backend.m_path = movie;
    backend.m_planMovie = QFileInfo(movie).absoluteFilePath();
    backend.m_planCuts = cuts;
    backend.m_launchProgram = stub;
    QSignalSpy noticeSpy(&backend, &Backend::notice);

    backend.writeCaptions();
    QVERIFY(backend.busy());
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QCOMPARE(backend.lastError(), QString());
    QCOMPARE(noticeSpy.count(), 1);
    QCOMPARE(noticeSpy.at(0).at(0).toString(), QStringLiteral("Wrote the captions"));
    const QString beside = QDir(savedDir).filePath(QStringLiteral("ride.srt"));
    QVERIFY(QFileInfo(beside).isFile());
    QVERIFY(QFileInfo(beside).size() > 0);
}

void BackendTests::qmlSentenceShowsTheLastError() {
    ShortcutBackend backend(QUrl(), 0.0);
    backend.setTray({QStringLiteral("/tmp/talk.mp4")});
    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(50);
    QQuickItem *sentence = window->findChild<QQuickItem *>(QStringLiteral("actionSentence"));
    QVERIFY(sentence);
    const QString usual = sentence->property("text").toString();
    QVERIFY(!usual.isEmpty());
    // The stub has no key, so this step already asks for something.
    const bool usualNeeds = window->property("actionNeedsYou").toBool();

    backend.setLastError(QStringLiteral("xAI connection failed"));
    QTRY_COMPARE(sentence->property("text").toString(), QStringLiteral("xAI connection failed"));
    QCOMPARE(window->property("actionNeedsYou").toBool(), true);

    backend.setLastError(QString());
    QTRY_COMPARE(sentence->property("text").toString(), usual);
    QCOMPARE(window->property("actionNeedsYou").toBool(), usualNeeds);
}

void BackendTests::qmlStopButtonCancelsTheJob() {
    ShortcutBackend backend(QUrl(), 0.0);
    backend.setTray({QStringLiteral("/tmp/talk.mp4")});
    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(50);
    QQuickItem *stop = window->findChild<QQuickItem *>(QStringLiteral("stopButton"));
    QVERIFY(stop);
    QVERIFY(!stop->isVisible());

    backend.setBusy(true);
    backend.setJob(QStringLiteral("Transcribing 1 of 3"));
    QTRY_VERIFY(stop->isVisible());
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(stop));
    QTRY_COMPARE(backend.cancelCount, 1);

    backend.setJob(QString());
    backend.setBusy(false);
    QTRY_VERIFY(!stop->isVisible());
}

void BackendTests::refusedKeyIsForgotten() {
    const QString refused = writeStubScript(m_dir.filePath(QStringLiteral("key-refused.sh")),
                                            "#!/bin/sh\necho 'xAI did not accept that key.' >&2\nexit 1\n");
    const QString offline = writeStubScript(m_dir.filePath(QStringLiteral("key-offline.sh")),
                                            "#!/bin/sh\necho 'Could not reach xAI to check the key.' >&2\nexit 1\n");
    const QString accepted = writeStubScript(m_dir.filePath(QStringLiteral("key-accepted.sh")),
                                             "#!/bin/sh\necho 'Key works'\nexit 0\n");
    QVERIFY(!refused.isEmpty() && !offline.isEmpty() && !accepted.isEmpty());

    ThumbProvider provider;
    MemoryKeyStore keys;
    Backend backend(&provider, new FakeFilePicker, &keys);
    // With no key there is nothing to ask about.
    backend.m_launchProgram = accepted;
    backend.checkApiKey();
    QVERIFY(!backend.busy());

    backend.setApiKey(QStringLiteral("supersecret"));
    backend.checkApiKey();
    QVERIFY(backend.busy());
    QCOMPARE(backend.job(), QStringLiteral("key"));
    QCOMPARE(backend.m_cutProcess->arguments(), QStringList{QStringLiteral("key")});
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QCOMPARE(backend.lastError(), QString());
    QVERIFY(!backend.m_apiKey.isEmpty());

    // The network being down says nothing about the key, so it stays.
    backend.m_launchProgram = offline;
    backend.checkApiKey();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QCOMPARE(backend.lastError(), QStringLiteral("Could not reach xAI to check the key."));
    QVERIFY(!backend.m_apiKey.isEmpty());

    backend.m_launchProgram = refused;
    backend.checkApiKey();
    QTRY_VERIFY_WITH_TIMEOUT(!backend.busy(), 5000);
    QCOMPARE(backend.lastError(), QStringLiteral("xAI did not accept that key."));
    QVERIFY(backend.m_apiKey.isEmpty());
    QVERIFY(keys.load().isEmpty());
}

void BackendTests::qmlSettingsSavesOnlyATypedKey() {
    ShortcutBackend backend(QUrl(), 0.0);
    QmlHarness harness(backend);
    QQuickWindow *window = harness.window();
    QVERIFY2(window, qPrintable(mainQmlPath()));
    window->show();
    window->resize(960, 640);
    QTest::qWait(50);
    QVERIFY(window->setProperty("settingsOpen", true));
    QTest::qWait(50);
    QQuickItem *save = window->findChild<QQuickItem *>(QStringLiteral("saveKeyButton"));
    QQuickItem *field = window->findChild<QQuickItem *>(QStringLiteral("keyField"));
    QVERIFY(save && field);
    // An empty field has nothing to save, so it cannot wipe the saved key.
    QCOMPARE(save->property("enabled").toBool(), false);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(save));
    QTest::qWait(20);
    QVERIFY(backend.savedKeys.isEmpty());

    QVERIFY(field->setProperty("text", QStringLiteral("  xai-typed  ")));
    QTRY_COMPARE(save->property("enabled").toBool(), true);
    // Done keeps a key that was typed and not yet saved, and has xAI check it.
    QQuickItem *done = visibleItemWithText(window, QStringLiteral("Done"));
    QVERIFY(done);
    QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, itemCenter(done));
    QTRY_COMPARE(backend.savedKeys.size(), 1);
    QCOMPARE(backend.savedKeys.first().trimmed(), QStringLiteral("xai-typed"));
    QCOMPARE(backend.keyCheckCount, 1);
    QTRY_COMPARE_WITH_TIMEOUT(window->property("settingsOpen").toBool(), false, 3000);
}

QTEST_MAIN(BackendTests)
#include "backend_tests.moc"
