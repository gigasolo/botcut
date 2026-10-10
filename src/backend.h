#pragma once

#include <QFileSystemWatcher>
#include <QHash>
#include <QImage>
#include <QObject>
#include <QProcess>
#include <QString>
#include <QStringList>
#include <QTimer>
#include <QUrl>
#include <QVariantList>
#include <QVector>

#include "cutjob.h"
#include "ffmpeg.h"
#include "keystore.h"
#include "timeline.h"

class ThumbProvider;
class FilePicker;
class ThumbWorker;
class TrayThumbWorker;

// The bridge between QML and the ffmpeg/ffprobe layer. Holds the currently
// loaded video's info and drives thumbnail generation and export.
class Backend : public QObject {
    Q_OBJECT
    Q_PROPERTY(QUrl source READ source NOTIFY infoChanged)
    Q_PROPERTY(double duration READ duration NOTIFY infoChanged)
    Q_PROPERTY(int thumbCount READ thumbCount NOTIFY thumbsChanged)
    Q_PROPERTY(int thumbReadyCount READ thumbReadyCount NOTIFY thumbsChanged)
    Q_PROPERTY(int thumbRevision READ thumbRevision NOTIFY thumbsChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QStringList tray READ tray NOTIFY trayChanged)
    Q_PROPERTY(int trayIndex READ trayIndex WRITE setTrayIndex NOTIFY trayChanged)
    Q_PROPERTY(QString cutMode READ cutMode WRITE setCutMode NOTIFY cutModeChanged)
    Q_PROPERTY(QString sceneTransition READ sceneTransition WRITE setSceneTransition NOTIFY sceneTransitionChanged)
    Q_PROPERTY(QString intent READ intent WRITE setIntent NOTIFY intentChanged)
    Q_PROPERTY(QVariantList selects READ selects NOTIFY selectsChanged)
    Q_PROPERTY(bool gathering READ gathering NOTIFY gatheringChanged)
    Q_PROPERTY(QUrl previewUrl READ previewUrl NOTIFY trayChanged)
    Q_PROPERTY(bool trayMissing READ trayMissing NOTIFY trayChanged)
    Q_PROPERTY(int trayThumbRevision READ trayThumbRevision NOTIFY trayThumbsChanged)
    Q_PROPERTY(bool apiKeySet READ apiKeySet NOTIFY apiKeyChanged)
    Q_PROPERTY(bool renderedUnsaved READ renderedUnsaved NOTIFY renderedUnsavedChanged)
    Q_PROPERTY(bool roughCut READ roughCut NOTIFY infoChanged)
    Q_PROPERTY(QString themeAccent READ themeAccent NOTIFY themeAccentChanged)
    Q_PROPERTY(QString themeAccentForeground READ themeAccentForeground NOTIFY themeAccentChanged)
    Q_PROPERTY(QObject *timeline READ timeline CONSTANT)

public:
    explicit Backend(ThumbProvider *provider, QObject *parent = nullptr);
    explicit Backend(ThumbProvider *provider, FilePicker *filePicker,
                     QObject *parent = nullptr);
    // `keys` is not owned. A null store becomes an owned empty memory store.
    Backend(ThumbProvider *provider, FilePicker *filePicker, KeyStore *keys,
            QObject *parent = nullptr);
    ~Backend() override;

    QUrl source() const { return m_source; }
    double duration() const { return m_info.duration; }
    int thumbCount() const { return m_thumbCount; }
    int thumbReadyCount() const { return m_thumbReadyCount; }
    int thumbRevision() const { return m_thumbRevision; }
    bool busy() const { return m_busy; }
    QString status() const { return m_status; }
    QStringList tray() const { return m_tray; }
    int trayIndex() const { return m_trayIndex; }
    QString cutMode() const { return m_cutMode; }
    QString sceneTransition() const { return m_sceneTransition; }
    QString intent() const { return m_intent; }
    QVariantList selects() const { return m_selects; }
    bool gathering() const { return m_gathering; }
    QUrl previewUrl() const;
    bool trayMissing() const;
    bool apiKeySet() const;
    bool renderedUnsaved() const { return m_renderedHere && !m_cutSaved; }
    bool roughCut() const;
    void setTrayIndex(int index);
    void setCutMode(const QString &mode);
    void setSceneTransition(const QString &value);
    void setIntent(const QString &intent);
    QString themeAccent() const { return m_themeAccent; }
    QString themeAccentForeground() const;
    Timeline *timeline() { return &m_timeline; }

    // The accent from an omarchy colors.toml, or the fallback when the file is
    // missing or holds no usable accent — which is what keeps omacut working on
    // distros without omarchy themes.
    static QString accentFromColorsFile(const QString &path, const QString &fallback);
    // "black" or "white", whichever stays legible on the given color.
    static QString foregroundFor(const QString &color);

    // Load a video (probes it, then kicks off thumbnail generation).
    Q_INVOKABLE bool load(const QUrl &url);
    Q_INVOKABLE bool loadKeepList(const QUrl &url);
    static bool parseKeepList(const QByteArray &json, const QString &baseDir, QString *source,
                              edit::Clips *clips, QString *error);

    // Open native desktop file dialogs.
    Q_INVOKABLE void openVideoDialog();
    Q_INVOKABLE void addVideosDialog();
    Q_INVOKABLE void addTrayFiles(const QStringList &paths);
    Q_INVOKABLE void addDropped(const QList<QUrl> &urls);
    Q_INVOKABLE bool trayFileExists(const QString &path) const;
    Q_INVOKABLE QString trayFileSize(const QString &path) const;
    Q_INVOKABLE QString trayThumb(const QString &path) const;
    int trayThumbRevision() const { return m_trayThumbRevision; }
    Q_INVOKABLE void moveTray(int delta);
    Q_INVOKABLE void removeTray();
    Q_INVOKABLE void openCutListDialog();
    Q_INVOKABLE void saveCutListDialog();
    Q_INVOKABLE void setApiKey(const QString &key);
    Q_INVOKABLE void startCut();
    Q_INVOKABLE void restoreSelect(int id);
    Q_INVOKABLE void dropSelect(int id);
    Q_INVOKABLE void renderSelects();
    Q_INVOKABLE void writeCaptions();
    Q_INVOKABLE void makeShort();
    // Exports the clips as they are when the dialog opens.
    Q_INVOKABLE void exportDialog();

    // Suggested "<name>_trimmed.mp4" target next to the source.
    Q_INVOKABLE QUrl suggestedExportUrl() const;

    // Write what the clips keep of the loaded video to dst. A non-zero
    // scaleHeight downscales the shorter side to that size.
    void exportClips(const QUrl &dst, const edit::Clips &clips, int scaleHeight = 0);

    // The downscale heights worth offering for a source: only ones strictly
    // below the source's shorter side, so exports never upscale.
    static QList<int> exportHeights(int width, int height);

    // Regenerate the filmstrip for [start, end] (seconds) — used by zoom.
    // The full-length strip is cached, so zooming back out restores instantly.
    Q_INVOKABLE void requestThumbs(double start, double end);
    Q_INVOKABLE void showShots();
    Q_INVOKABLE void showMovie();

signals:
    void infoChanged();
    void thumbsChanged();
    void busyChanged();
    void statusChanged();
    void trayChanged();
    void trayThumbsChanged();
    void cutModeChanged();
    void sceneTransitionChanged();
    void intentChanged();
    void selectsChanged();
    void gatheringChanged();
    void apiKeyChanged();
    void themeAccentChanged();
    void exportDone(const QString &path);
    void exportFailed(const QString &message);
    void renderedUnsavedChanged();
    void loadError(const QString &message);

private:
    void setBusy(bool busy);
    void setStatus(const QString &status);
    void failExport(const QString &tmpPath, const QString &message);
    void copyCut(const QUrl &dst);
    void noteCutSaved(const QString &path);
    void startThumbs();
    void stopThumbs();
    void scheduleTrayThumbs();
    void stopTrayThumbs();
    void revealNextThumb();
    void wireFilePicker();
    void loadThemeAccent();
    void watchTheme();
    void startCutProcess(const CutLaunch &launch);
    void readCutOutput();
    void cutProcessFinished(int code, QProcess::ExitStatus status);
    void loadCutListFile(const QUrl &url);
    void writeCutListFile(const QUrl &url);
    bool writeCutsForRender();
    QString cutsBesideMovie() const;
    void loadSelects(const QString &cutsPath);
    bool writeSelects(const QString &cutsPath) const;
    QString intentForCut() const;
    QUrl suggestedCutListUrl() const;
    Backend(ThumbProvider *provider, FilePicker *filePicker, KeyStore *keys, bool ownsKeys,
            QObject *parent);

    ThumbProvider *m_provider;
    FilePicker *m_filePicker;
    ThumbWorker *m_thumbWorker = nullptr;
    TrayThumbWorker *m_trayThumbWorker = nullptr;
    QHash<QString, QString> m_trayThumbs;
    int m_trayThumbRevision = 0;
    friend class BackendTests;
    Timeline m_timeline;
    edit::Clips m_exportDialogClips;
    ffmpeg::VideoInfo m_info;
    QString m_path;
    QUrl m_source;
    double m_thumbStart = 0.0;
    double m_thumbLen = 0.0;
    QVector<QImage> m_fullThumbs;
    bool m_fullThumbsComplete = false;
    int m_thumbCount = 0;
    int m_thumbAvailableCount = 0;
    int m_thumbReadyCount = 0;
    int m_thumbRevision = 0;
    bool m_thumbWorkerDone = false;
    bool m_busy = false;
    QString m_status;
    QStringList m_tray;
    int m_trayIndex = -1;
    QString m_cutMode = QStringLiteral("speech");
    QString m_sceneTransition = QStringLiteral("dip");
    QString m_intent;
    QVariantList m_selects;
    bool m_gathering = true;
    QString m_apiKey;
    KeyStore *m_keys = nullptr;
    bool m_ownsKeys = false;
    QString m_cutOut;
    bool m_renderedHere = false;
    bool m_cutSaved = false;
    enum class CutStage { Idle, Decide, Run, Render, Review, Captions, Short };
    CutStage m_cutStage = CutStage::Idle;
    void startBesideCut(CutStage stage, const QString &running,
                        CutLaunch (*make)(const QString &, const QString &, const QString &,
                                          const QString &));
    QProcess *m_cutProcess = nullptr;
    QString m_cutLog;
    QString m_cutLine;
    QString m_themeAccent;
    QTimer m_thumbRevealTimer;
    QFileSystemWatcher m_themeWatcher;
};
