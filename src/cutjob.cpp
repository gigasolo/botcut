#include "cutjob.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>

#include <cerrno>
#include <sys/stat.h>
#include <unistd.h>

namespace {

CutLaunch launchTool(const QStringList &tail, const QString &botcutCli, const QString &uv,
                     const QString &cliProject) {
    CutLaunch launch;
    if (!botcutCli.isEmpty()) {
        launch.program = botcutCli;
        launch.arguments = tail;
        return launch;
    }
    if (!uv.isEmpty() && !cliProject.isEmpty()) {
        launch.program = uv;
        launch.arguments << QStringLiteral("run") << QStringLiteral("--project") << cliProject
                         << QStringLiteral("botcut-cli") << tail;
        return launch;
    }
    launch.error = QStringLiteral(
        "botcut-cli was not found. Install it, or put uv on PATH with ~/code/botcut/cli.");
    return launch;
}

QString sceneTransitionValue(const QString &value) {
    return value == QLatin1String("off") ? QStringLiteral("off") : QStringLiteral("dip");
}

QString paceValue(const QString &pace) {
    if (pace == QLatin1String("measured") || pace == QLatin1String("tight")
        || pace == QLatin1String("frenzied"))
        return pace;
    return QStringLiteral("open");
}

}

QString defaultCutIntent() {
    return QStringLiteral(
        "Keep each moment in order. Drop flubs and true retakes. Keep a beat that appears only once.");
}

CutLaunch cutRunLaunch(const QStringList &files, const QString &mode, const QString &outDir,
                       const QString &botcutCli, const QString &uv, const QString &cliProject,
                       const QString &intent, bool decide, const QString &sceneTransition,
                       double maxPause) {
    if (files.isEmpty())
        return {QString(), {}, QStringLiteral("Add a video first")};
    if (mode != QLatin1String("speech") && mode != QLatin1String("assemble"))
        return {QString(), {}, QStringLiteral("Unknown cut mode")};
    if (outDir.isEmpty())
        return {QString(), {}, QStringLiteral("No output directory")};
    QStringList tail{QStringLiteral("run")};
    tail << files << QStringLiteral("--out") << outDir << QStringLiteral("--mode") << mode;
    const QString movie = intent.trimmed().isEmpty() ? defaultCutIntent() : intent.trimmed();
    tail << QStringLiteral("--intent") << movie;
    tail << QStringLiteral("--scene-transition") << sceneTransitionValue(sceneTransition);
    tail << QStringLiteral("--max-pause") << QString::number(maxPause);
    if (decide)
        tail << QStringLiteral("--decide");
    return launchTool(tail, botcutCli, uv, cliProject);
}

CutLaunch cutRenderLaunch(const QString &outDir, const QString &botcutCli, const QString &uv,
                          const QString &cliProject, const QString &sceneTransition) {
    if (outDir.isEmpty())
        return {QString(), {}, QStringLiteral("No output directory")};
    const QStringList tail{QStringLiteral("render"), outDir, QStringLiteral("--scene-transition"),
                           sceneTransitionValue(sceneTransition)};
    return launchTool(tail, botcutCli, uv, cliProject);
}

CutLaunch cutReviewLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                          const QString &cliProject) {
    if (cutsPath.isEmpty())
        return {QString(), {}, QStringLiteral("No cuts.json")};
    const QStringList tail{QStringLiteral("review"), cutsPath, QStringLiteral("--no-open")};
    return launchTool(tail, botcutCli, uv, cliProject);
}

CutLaunch cutCaptionsLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                            const QString &cliProject) {
    if (cutsPath.isEmpty())
        return {QString(), {}, QStringLiteral("No cuts.json")};
    const QStringList tail{QStringLiteral("captions"), cutsPath};
    return launchTool(tail, botcutCli, uv, cliProject);
}

CutLaunch cutShortLaunch(const QString &cutsPath, const QString &botcutCli, const QString &uv,
                         const QString &cliProject) {
    if (cutsPath.isEmpty())
        return {QString(), {}, QStringLiteral("No cuts.json")};
    const QStringList tail{QStringLiteral("short"), cutsPath};
    return launchTool(tail, botcutCli, uv, cliProject);
}

CutLaunch cutReviseLaunch(const QString &cutsPath, const QString &note, const QString &botcutCli,
                          const QString &uv, const QString &cliProject, const QString &pace,
                          const QString &sceneTransition) {
    if (cutsPath.isEmpty())
        return {QString(), {}, QStringLiteral("No cuts.json")};
    const QString trimmed = note.simplified();
    if (trimmed.isEmpty())
        return {QString(), {}, QStringLiteral("Say what to change")};
    // `--` keeps a note such as --help from being parsed as an option.
    const QStringList tail{QStringLiteral("revise"), cutsPath, QStringLiteral("--pace"),
                           paceValue(pace), QStringLiteral("--scene-transition"),
                           sceneTransitionValue(sceneTransition), QStringLiteral("--"), trimmed};
    return launchTool(tail, botcutCli, uv, cliProject);
}

QString cardDirectory() {
    const QByteArray xdg = qgetenv("XDG_DATA_HOME");
    const QString base = xdg.isEmpty()
                             ? QDir::home().filePath(QStringLiteral(".local/share"))
                             : QFileInfo(QString::fromLocal8Bit(xdg)).absoluteFilePath();
    return QDir(base).filePath(QStringLiteral("botcut/cards"));
}

QString ensureCardDirectory(QString *canonical) {
    const QString path = cardDirectory();
    if (!QDir().mkpath(QFileInfo(path).dir().absolutePath()))
        return QStringLiteral("No card directory");
    const QByteArray encoded = QFile::encodeName(path);
    if (::mkdir(encoded.constData(), 0700) != 0 && errno != EEXIST)
        return QStringLiteral("No card directory");
    const QFileInfo info(path);
    if (info.isSymbolicLink() || !info.isDir())
        return QStringLiteral("No card directory");
    if (info.ownerId() != static_cast<uint>(::getuid()))
        return QStringLiteral("No card directory");
    const QFile::Permissions perms = info.permissions();
    if (!perms.testFlag(QFileDevice::WriteOwner) || perms.testFlag(QFileDevice::WriteGroup)
        || perms.testFlag(QFileDevice::WriteOther))
        return QStringLiteral("No card directory");
    const QString real = info.canonicalFilePath();
    if (real.isEmpty())
        return QStringLiteral("No card directory");
    if (canonical != nullptr)
        *canonical = real;
    return {};
}

QString cardDestinationError(const QString &dest) {
    static const QRegularExpression nameRe(
        QStringLiteral("^botcut-card-[A-Za-z0-9][A-Za-z0-9_-]*\\.mp4$"));
    const QFileInfo info(dest);
    if (!nameRe.match(info.fileName()).hasMatch() || info.isSymbolicLink())
        return QStringLiteral("No card file");
    const QFileInfo root(cardDirectory());
    if (root.isSymbolicLink() || !root.isDir() || root.ownerId() != static_cast<uint>(::getuid()))
        return QStringLiteral("No card file");
    const QFile::Permissions perms = root.permissions();
    if (!perms.testFlag(QFileDevice::WriteOwner) || perms.testFlag(QFileDevice::WriteGroup)
        || perms.testFlag(QFileDevice::WriteOther))
        return QStringLiteral("No card file");
    const QString rootReal = root.canonicalFilePath();
    const QString parentReal = info.dir().canonicalPath();
    if (rootReal.isEmpty() || parentReal.isEmpty() || parentReal != rootReal)
        return QStringLiteral("No card file");
    if (info.exists()) {
        const QString real = info.canonicalFilePath();
        if (real.isEmpty() || QFileInfo(real).dir().canonicalPath() != rootReal)
            return QStringLiteral("No card file");
    }
    return {};
}

CutLaunch cutCardLaunch(const QString &dest, const QString &sentence, const QString &botcutCli,
                        const QString &uv, const QString &cliProject) {
    const QString trimmed = sentence.simplified();
    if (trimmed.isEmpty())
        return {QString(), {}, QStringLiteral("Say what the card says")};
    const QString problem = cardDestinationError(dest);
    if (!problem.isEmpty())
        return {QString(), {}, problem};
    const QString absolute = QFileInfo(dest).absoluteFilePath();
    const QStringList tail{QStringLiteral("card"), QStringLiteral("--out"), absolute,
                           QStringLiteral("--"), trimmed};
    return launchTool(tail, botcutCli, uv, cliProject);
}

bool parseCutList(const QByteArray &json, const QString &baseDir, QString *mode, QStringList *files,
                  QString *error, QString *intent, QVariantList *lines) {
    const QJsonDocument doc = QJsonDocument::fromJson(json);
    if (!doc.isObject()) {
        *error = QStringLiteral("Cut list is not a JSON object");
        return false;
    }
    const QJsonObject root = doc.object();
    if (root.value(QStringLiteral("version")).toInt() != 1) {
        *error = QStringLiteral("Cut list version is not 1");
        return false;
    }
    const QString parsedMode = root.value(QStringLiteral("mode")).toString();
    if (parsedMode != QLatin1String("speech") && parsedMode != QLatin1String("assemble")) {
        *error = QStringLiteral("Cut list mode is unknown");
        return false;
    }
    const QJsonValue filesValue = root.value(QStringLiteral("files"));
    if (!filesValue.isArray() || filesValue.toArray().isEmpty()) {
        *error = QStringLiteral("Cut list has no files");
        return false;
    }
    QStringList parsed;
    const QJsonArray array = filesValue.toArray();
    for (int i = 0; i < array.size(); ++i) {
        if (!array.at(i).isString() || array.at(i).toString().isEmpty()) {
            *error = QStringLiteral("Cut list file %1 is invalid").arg(i + 1);
            return false;
        }
        const QString path = array.at(i).toString();
        const QFileInfo info(path);
        parsed.append(info.isRelative() ? QDir(baseDir).absoluteFilePath(path) : info.absoluteFilePath());
    }
    *mode = parsedMode;
    *files = parsed;
    if (intent != nullptr) {
        const QString parsedIntent = root.value(QStringLiteral("intent")).toString().trimmed();
        *intent = parsedIntent.isEmpty() ? defaultCutIntent() : parsedIntent;
    }
    if (lines != nullptr) {
        lines->clear();
        const QJsonValue linesValue = root.value(QStringLiteral("lines"));
        if (!linesValue.isUndefined() && !linesValue.isNull()) {
            if (!linesValue.isArray()) {
                *error = QStringLiteral("Cut list lines are invalid");
                return false;
            }
            for (const QJsonValue &value : linesValue.toArray()) {
                if (!value.isObject()) {
                    *error = QStringLiteral("Cut list lines are invalid");
                    return false;
                }
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
                               stillInfo.isRelative() ? QDir(baseDir).absoluteFilePath(still)
                                                      : stillInfo.absoluteFilePath());
                }
                lines->append(row);
            }
        }
    }
    return true;
}

QByteArray writeCutList(const QString &mode, const QStringList &files, const QString &intent,
                        const QVariantList &lines) {
    if ((mode != QLatin1String("speech") && mode != QLatin1String("assemble")) || files.isEmpty())
        return {};
    QJsonArray array;
    for (const QString &path : files)
        array.append(QFileInfo(path).absoluteFilePath());
    const QString movie = intent.trimmed().isEmpty() ? defaultCutIntent() : intent.trimmed();
    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("mode"), mode);
    root.insert(QStringLiteral("intent"), movie);
    root.insert(QStringLiteral("files"), array);
    if (!lines.isEmpty()) {
        QJsonArray lineArray;
        for (const QVariant &item : lines) {
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
            lineArray.append(line);
        }
        root.insert(QStringLiteral("lines"), lineArray);
    }
    return QJsonDocument(root).toJson(QJsonDocument::Indented);
}

QProcessEnvironment cutProcessEnvironment(const QProcessEnvironment &base, const QString &uiKey) {
    QProcessEnvironment env = base;
    if (!uiKey.isEmpty())
        env.insert(QStringLiteral("XAI_API_KEY"), uiKey);
    return env;
}

QString cutStatusFromLine(const QString &line) {
    const QString trimmed = line.trimmed();
    if (trimmed.isEmpty() || trimmed.size() > 200)
        return {};
    if (trimmed == QLatin1String("Reading files") || trimmed == QLatin1String("Reading pictures")
        || trimmed == QLatin1String("Choosing takes") || trimmed == QLatin1String("Trying again")
        || trimmed == QLatin1String("Revising"))
        return trimmed;
    static const QRegularExpression decided(QStringLiteral("^\\d+ kept, \\d+ dropped$"));
    if (decided.match(trimmed).hasMatch())
        return trimmed;
    static const QRegularExpression transcribing(
        QStringLiteral("^Transcribing [1-9]\\d*/[1-9]\\d* \\S.*$"));
    static const QRegularExpression percent(
        QStringLiteral("^(?:Rendering|Opening) (?:100|[1-9]?\\d)%$"));
    if (transcribing.match(trimmed).hasMatch() || percent.match(trimmed).hasMatch())
        return trimmed;
    return {};
}
