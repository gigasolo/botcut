// Theme watching follows Omacut (MIT, David Heinemeier Hansson).
#include "theme.h"

#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QStandardPaths>
#include <cmath>

Theme::Theme(const QString &directory, QObject *parent, const QString &hyprctl)
    : QObject(parent),
      m_directory(directory.isEmpty() ? QDir::homePath() + QStringLiteral("/.local/state/omarchy/current")
                                      : directory) {
    m_debounce.setSingleShot(true);
    m_debounce.setInterval(80);
    connect(&m_watcher, &QFileSystemWatcher::directoryChanged, this, [this] { m_debounce.start(); });
    connect(&m_watcher, &QFileSystemWatcher::fileChanged, this, [this] { m_debounce.start(); });
    connect(&m_debounce, &QTimer::timeout, this, &Theme::reload);

    // Corners follow Hyprland's effective rounding. Themes and personal
    // overrides can both set it, so ask hyprctl rather than reading its config.
    // Without Hyprland the corners stay sharp, like Omarchy's default.
    m_hyprctl = !hyprctl.isEmpty() ? hyprctl
              : directory.isEmpty() && !qEnvironmentVariableIsEmpty("HYPRLAND_INSTANCE_SIGNATURE")
                  ? QStandardPaths::findExecutable(QStringLiteral("hyprctl")) : QString();
    m_roundingTimeout.setSingleShot(true);
    m_roundingTimeout.setInterval(500);
    connect(&m_roundingTimeout, &QTimer::timeout, &m_roundingProcess, &QProcess::kill);
    connect(&m_roundingProcess, &QProcess::errorOccurred, this, [this] { m_roundingTimeout.stop(); });
    connect(&m_roundingProcess, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
        m_roundingTimeout.stop();
        const auto value = QJsonDocument::fromJson(m_roundingProcess.readAllStandardOutput()).object().value(QStringLiteral("int"));
        if (code != 0 || status != QProcess::NormalExit || !value.isDouble() || value.toInt(-1) < 0)
            return;
        if (value.toInt() != m_radius) {
            m_radius = value.toInt();
            emit changed();
        }
    });
    m_roundingPoll.setInterval(1000);
    connect(&m_roundingPoll, &QTimer::timeout, this, &Theme::refreshRounding);
    if (!m_hyprctl.isEmpty())
        m_roundingPoll.start();
    reload();
}

Theme::~Theme() {
    if (m_roundingProcess.state() != QProcess::NotRunning) {
        m_roundingProcess.kill();
        m_roundingProcess.waitForFinished(1000);
    }
}

void Theme::refreshRounding() {
    if (m_hyprctl.isEmpty() || m_roundingProcess.state() != QProcess::NotRunning)
        return;
    m_roundingProcess.start(m_hyprctl, {QStringLiteral("-j"), QStringLiteral("getoption"),
                                        QStringLiteral("decoration:rounding")});
    m_roundingTimeout.start();
}

QString Theme::readColor(const QString &path, const QString &key, const QString &fallback) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return fallback;
    const QRegularExpression expression(
        QStringLiteral("^\\s*%1\\s*=\\s*[\"'](#[0-9a-fA-F]{6})[\"']").arg(QRegularExpression::escape(key)),
        QRegularExpression::MultilineOption);
    const auto match = expression.match(QString::fromUtf8(file.readAll()));
    return match.hasMatch() ? match.captured(1) : fallback;
}

QString Theme::accentForeground() const {
    const QColor c(m_accent);
    auto linear = [](double v) { return v <= .04045 ? v / 12.92 : std::pow((v + .055) / 1.055, 2.4); };
    const double luminance = .2126 * linear(c.redF()) + .7152 * linear(c.greenF()) + .0722 * linear(c.blueF());
    return luminance > .179 ? QStringLiteral("black") : QStringLiteral("white");
}

void Theme::reload() {
    refreshRounding();
    const auto paths = m_watcher.files() + m_watcher.directories();
    if (!paths.isEmpty())
        m_watcher.removePaths(paths);

    // A theme switch replaces symlinks and files, so watch the parents too and
    // re-arm after every change.
    QString ancestor = m_directory;
    while (!QFileInfo::exists(ancestor) && ancestor != QLatin1String("/"))
        ancestor = QFileInfo(ancestor).absolutePath();
    QStringList candidates{ancestor, QFileInfo(ancestor).absolutePath(), m_directory,
                           m_directory + QStringLiteral("/theme"),
                           m_directory + QStringLiteral("/theme/colors.toml")};
    candidates.removeDuplicates();
    for (const auto &path : candidates)
        if (QFileInfo::exists(path))
            m_watcher.addPath(path);

    const QString colors = m_directory + QStringLiteral("/theme/colors.toml");
    const QString accent = readColor(colors, QStringLiteral("accent"), QStringLiteral("#FFD60A"));
    const QString foreground = readColor(colors, QStringLiteral("foreground"), QStringLiteral("#f4f4f5"));
    const QString background = readColor(colors, QStringLiteral("background"), QStringLiteral("#0e0e10"));
    if (accent == m_accent && foreground == m_foreground && background == m_background)
        return;
    m_accent = accent;
    m_foreground = foreground;
    m_background = background;
    emit changed();
}
