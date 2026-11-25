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
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

Theme::Theme(const QString &directory, QObject *parent, const QString &hyprctl)
    : QObject(parent),
      m_directory(directory.isEmpty() ? QDir::homePath() + QStringLiteral("/.local/state/omarchy/current")
                                      : directory) {
    recomputeDerived();
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
    if (directory.isEmpty() && !m_hyprctl.isEmpty())
        connectHyprlandSocket();
    reload();
}

Theme::~Theme() {
    closeHyprlandSocket();
    if (m_roundingProcess.state() != QProcess::NotRunning) {
        m_roundingProcess.kill();
        m_roundingProcess.waitForFinished(1000);
    }
}

void Theme::connectHyprlandSocket() {
    const QString sig = QString::fromUtf8(qgetenv("HYPRLAND_INSTANCE_SIGNATURE"));
    const QString runtime = QString::fromUtf8(qgetenv("XDG_RUNTIME_DIR"));
    if (sig.isEmpty() || runtime.isEmpty())
        return;
    const QByteArray sockPath =
        (runtime + QStringLiteral("/hypr/") + sig + QStringLiteral("/.socket2.sock")).toUtf8();
    struct sockaddr_un addr {};
    if (sockPath.size() >= static_cast<qsizetype>(sizeof(addr.sun_path)))
        return;
    const int fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return;
    addr.sun_family = AF_UNIX;
    std::memcpy(addr.sun_path, sockPath.constData(), static_cast<size_t>(sockPath.size()) + 1);
    if (::connect(fd, reinterpret_cast<struct sockaddr *>(&addr), sizeof(addr)) != 0
        && errno != EINPROGRESS) {
        ::close(fd);
        return;
    }
    m_hyprFd = fd;
    m_hyprNotifier = new QSocketNotifier(m_hyprFd, QSocketNotifier::Read, this);
    connect(m_hyprNotifier, &QSocketNotifier::activated, this, &Theme::readHyprlandEvents);
}

void Theme::readHyprlandEvents() {
    if (m_hyprFd < 0)
        return;
    char buf[1024];
    for (;;) {
        const ssize_t n = ::read(m_hyprFd, buf, sizeof(buf));
        if (n > 0) {
            m_hyprBuffer.append(buf, static_cast<qsizetype>(n));
            continue;
        }
        if (n == 0) {
            closeHyprlandSocket();
            return;
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK)
            break;
        closeHyprlandSocket();
        return;
    }
    bool reloadRounding = false;
    int newline = -1;
    while ((newline = m_hyprBuffer.indexOf('\n')) >= 0) {
        const QByteArray line = m_hyprBuffer.left(newline);
        m_hyprBuffer.remove(0, newline + 1);
        if (line.startsWith("configreloaded>>"))
            reloadRounding = true;
    }
    if (m_hyprBuffer.size() > 8192)
        m_hyprBuffer.clear();
    if (reloadRounding)
        refreshRounding();
}

void Theme::closeHyprlandSocket() {
    if (m_hyprNotifier) {
        m_hyprNotifier->setEnabled(false);
        m_hyprNotifier->deleteLater();
        m_hyprNotifier = nullptr;
    }
    if (m_hyprFd >= 0) {
        ::close(m_hyprFd);
        m_hyprFd = -1;
    }
    m_hyprBuffer.clear();
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

QString Theme::mixToward(const QString &background, const QString &foreground, double amount) {
    const QColor from(background);
    const QColor to(foreground);
    if (!from.isValid() || !to.isValid())
        return background;
    const auto channel = [amount](int start, int end) {
        return std::clamp(static_cast<int>(std::lround(start + (end - start) * amount)), 0, 255);
    };
    return QColor(channel(from.red(), to.red()), channel(from.green(), to.green()),
                  channel(from.blue(), to.blue()))
        .name(QColor::HexRgb);
}

void Theme::recomputeDerived() {
    // Amounts are tuned so the Omarchy defaults (#0e0e10 toward #f4f4f5) land
    // near the old flat surfaces. They are not a second palette.
    m_surface = mixToward(m_background, m_foreground, 0.06);
    m_raised = mixToward(m_background, m_foreground, 0.13);
    m_selected = mixToward(m_background, m_foreground, 0.12);
    m_hover = mixToward(m_background, m_foreground, 0.19);
    m_line = mixToward(m_background, m_foreground, 0.187);
    // One modal veil. Dialogs used #99000000; the quit card used #000000cc.
    m_scrim = QStringLiteral("#99000000");
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
    recomputeDerived();
    emit changed();
}
