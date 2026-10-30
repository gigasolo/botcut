#pragma once

#include <QFileSystemWatcher>
#include <QObject>
#include <QProcess>
#include <QTimer>

// Follows the Omarchy accent, foreground, and background live, and Hyprland's
// window rounding as radius. Tests pass a temp directory and a fake hyprctl.
class Theme : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString accent READ accent NOTIFY changed)
    Q_PROPERTY(QString accentForeground READ accentForeground NOTIFY changed)
    Q_PROPERTY(QString foreground READ foreground NOTIFY changed)
    Q_PROPERTY(QString background READ background NOTIFY changed)
    Q_PROPERTY(int radius READ radius NOTIFY changed)

public:
    explicit Theme(const QString &currentDirectory = {}, QObject *parent = nullptr,
                   const QString &hyprctl = {});
    ~Theme() override;

    QString accent() const { return m_accent; }
    QString accentForeground() const;
    QString foreground() const { return m_foreground; }
    QString background() const { return m_background; }
    int radius() const { return m_radius; }

    static QString readColor(const QString &path, const QString &key, const QString &fallback);

signals:
    void changed();

private:
    void reload();
    void refreshRounding();

    QString m_directory;
    QString m_accent = QStringLiteral("#FFD60A");
    QString m_foreground = QStringLiteral("#f4f4f5");
    QString m_background = QStringLiteral("#0e0e10");
    QFileSystemWatcher m_watcher;
    QTimer m_debounce;
    QString m_hyprctl;
    int m_radius = 0;
    QProcess m_roundingProcess;
    QTimer m_roundingPoll;
    QTimer m_roundingTimeout;
};
