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
                       const QString &sceneTransition = QStringLiteral("dip"));

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
