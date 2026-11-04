#pragma once

#include <QVariantMap>

#include "filepicker.h"

class PortalFilePicker : public FilePicker {
    Q_OBJECT

public:
    explicit PortalFilePicker(QObject *parent = nullptr);

    void openVideo() override;
    void openVideos() override;
    void openCutList() override;
    void saveCutList(const QUrl &suggestedUrl) override;
    void exportVideo(const QUrl &suggestedUrl, const QList<int> &scaleHeights,
                     int sourceWidth, int sourceHeight) override;

protected:
    enum class Action {
        None,
        Open,
        Add,
        OpenList,
        SaveList,
        Export
    };

    virtual void requestFile(const QString &method, const QString &title,
                             QVariantMap options, Action action);
    // Quality combo from a submitted export request. Empty when the request offers none.
    static QVariantMap qualityChoice(const QVariantMap &options);

private slots:
    void handleResponse(uint response, const QVariantMap &results);

private:
    bool connectToRequestPath(const QString &path);
    void clearPending();

    QString m_pendingPath;
    Action m_pendingAction = Action::None;
};
