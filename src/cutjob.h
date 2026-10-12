#pragma once

#include <QByteArray>
#include <QProcessEnvironment>
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
                       double maxPause = 0.8);

CutLaunch cutRenderLaunch(const QString &outDir, const QString &botcutCli, const QString &uv,
                          const QString &cliProject,
                          const QString &sceneTransition = QStringLiteral("dip"));

CutLaunch cutReviewLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                          const QString &cliProject);

// captions and short take the cuts.json file. A directory is not a valid path.
CutLaunch cutCaptionsLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                            const QString &cliProject);

CutLaunch cutShortLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                         const QString &cliProject);

// Pace is a name. --max-pause is applied by the next Cut or Render, not here.
CutLaunch cutReviseLaunch(const QString &cutsPath, const QString &note, const QString &botcutCli,
                          const QString &uv, const QString &cliProject, const QString &pace,
                          const QString &sceneTransition);

// The sentence is positional. `--` keeps it from being read as an option.
// The output name starts with botcut-card- so a later spoken cut can see it.
CutLaunch cutCardLaunch(const QString &dest, const QString &sentence, const QString &botcutCli,
                        const QString &uv, const QString &cliProject);

// Cards live under XDG data, not the temp dir, so a saved list can open them after a restart.
// Empty means the directory is real, owned by this user, and not writable by anyone else.
QString ensureCardDirectory(QString *canonical);

// Empty when dest is one botcut-card-*.mp4 inside that directory. A symlink or any other
// directory is refused before a process starts.
QString cardDestinationError(const QString &dest);

// Shot list on disk: version, mode, intent, absolute paths, and optional line
// decisions. No API key. A list with no lines still opens.
bool parseCutList(const QByteArray &json, const QString &baseDir, QString *mode, QStringList *files,
                  QString *error, QString *intent = nullptr, QVariantList *lines = nullptr);
QByteArray writeCutList(const QString &mode, const QStringList &files, const QString &intent = QString(),
                        const QVariantList &lines = {});

// Child environment for botcut-cli. A typed key is inserted here, never into argv.
QProcessEnvironment cutProcessEnvironment(const QProcessEnvironment &base, const QString &uiKey);

// A short CLI status line for the tray, or empty when the line is not one.
QString cutStatusFromLine(const QString &line);
