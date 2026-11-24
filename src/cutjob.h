#pragma once

#include <QByteArray>
#include <QProcessEnvironment>
#include <QJsonArray>
#include <QJsonValue>
#include <QString>
#include <QStringList>
#include <QVariantList>

// How the empty-window Cut button starts botcut-cli. Pure data so the
// offscreen tests can lock the command without opening a file dialog.
struct CutLaunch {
    QString program;
    QStringList arguments;
    QString error;
};

QString defaultCutIntent();

CutLaunch cutRunLaunch(const QStringList &files, const QString &mode, const QString &outDir,
                       const QString &botcutCli, const QString &uv, const QString &cliProject,
                       const QString &intent = QString(), bool decide = false,
                       const QString &sceneTransition = QStringLiteral("dip"),
                       double maxPause = 0.8, const QStringList &brollFiles = {},
                       bool brollMix = true, const QString &zoom = QStringLiteral("off"),
                       const QStringList &angleFiles = {},
                       const QString &resolution = QStringLiteral("source"),
                       const QString &aspect = QStringLiteral("source"),
                       bool pip = false,
                       const QString &liveTitle = QString());

CutLaunch cutRenderLaunch(const QString &outDir, const QString &botcutCli, const QString &uv,
                          const QString &cliProject,
                          const QString &sceneTransition = QStringLiteral("dip"),
                          bool brollMix = true, const QString &zoom = QStringLiteral("off"),
                          const QString &resolution = QStringLiteral("source"),
                          const QString &aspect = QStringLiteral("source"),
                          const QString &outFile = QString(),
                          bool pip = false,
                          const QString &liveTitle = QString());

// The zoom on the speaker: off, or auto. The command line's cuts, push, and lines still pass. Anything else is off.
QString zoomValue(const QString &zoom);
// Output resolution: source, 2160p, 1440p, 1080p, or 720p. Anything else is source.
QString resolutionValue(const QString &resolution);
// Output aspect ratio: source, landscape, or portrait. Anything else is source.
QString aspectValue(const QString &aspect);


// captions and short take the cuts.json file. A directory is not a valid path.
CutLaunch cutCaptionsLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                            const QString &cliProject);

CutLaunch cutShortLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                         const QString &cliProject);
// Asks xAI whether it accepts the key in the environment. No files.
// The cuts on offer inside a line, between cuts.json and the window. Each is
// {from, through, start, end, reason, cut}: word positions, the seconds they
// span in the shot, and whether it is taken.
QVariantList wordCutsFromJson(const QJsonValue &value);
QJsonArray wordCutsToJson(const QVariantList &cuts);
CutLaunch cutKeyLaunch(const QString &botcutCli, const QString &uv, const QString &cliProject);

// Pace is a name. --max-pause is applied by the next Cut or Render, not here.
// With propose, the CLI writes proposal.json beside cuts.json and leaves the
// lines alone; history names a JSON file of earlier chat turns.
CutLaunch cutReviseLaunch(const QString &cutsPath, const QString &note, const QString &botcutCli,
                          const QString &uv, const QString &cliProject, const QString &pace,
                          const QString &sceneTransition, bool propose = false,
                          const QString &history = QString());

// Lands the proposal.json a propose wrote. No note, no model call.
CutLaunch cutApplyLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                         const QString &cliProject);

// The sentence is positional. `--` keeps it from being read as an option.
// The output name starts with botcut-card- so a later spoken cut can see it.
CutLaunch cutCardLaunch(const QString &dest, const QString &sentence, const QString &botcutCli,
                        const QString &uv, const QString &cliProject,
                        const QString &style = QStringLiteral("ai"),
                        const QString &fromVideo = QString(),
                        const QString &aspect = QStringLiteral("landscape"));

CutLaunch cutThumbLaunch(const QString &cutsPath, const QString &title, const QString &outJpg,
                         const QString &outCardMp4, const QString &aspect, bool embed,
                         const QString &botcutCli, const QString &uv, const QString &cliProject);

CutLaunch cutShipLaunch(const QString &cutsPath, const QString &outDir, const QString &title,
                        const QString &resolution, bool includePortrait,
                        const QString &botcutCli, const QString &uv, const QString &cliProject);

// Cards live under XDG data, not the temp dir, so a saved list can open them after a restart.
// Empty means the directory is real, owned by this user, and not writable by anyone else.
QString ensureCardDirectory(QString *canonical);

// Empty when dest is one botcut-card-*.mp4 inside that directory. A symlink or any other
// directory is refused before a process starts.
QString cardDestinationError(const QString &dest);

// Shot list on disk: version, mode, intent, absolute paths, optional line
// decisions, and the files marked B-roll. No API key. A list with no lines
// still opens, and so does an older list with no "broll".
bool parseCutList(const QByteArray &json, const QString &baseDir, QString *mode, QStringList *files,
                  QString *error, QString *intent = nullptr, QVariantList *lines = nullptr,
                  QStringList *brollFiles = nullptr, QStringList *angleFiles = nullptr);
QByteArray writeCutList(const QString &mode, const QStringList &files, const QString &intent = QString(),
                        const QVariantList &lines = {}, const QStringList &brollFiles = {},
                        const QStringList &angleFiles = {});

// Child environment for botcut-cli. A typed key is inserted here, never into argv.
QProcessEnvironment cutProcessEnvironment(const QProcessEnvironment &base, const QString &uiKey);

// A short CLI status line for the tray, or empty when the line is not one.
QString cutStatusFromLine(const QString &line);
