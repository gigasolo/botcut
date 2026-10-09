#pragma once

#include <QList>
#include <QObject>
#include <QUrl>

class FilePicker : public QObject {
    Q_OBJECT

public:
    explicit FilePicker(QObject *parent = nullptr) : QObject(parent) {}
    virtual ~FilePicker() = default;

    virtual void openVideo() = 0;
    virtual void openVideos() = 0;
    virtual void openCutList() = 0;
    virtual void saveCutList(const QUrl &suggestedUrl) = 0;
    // scaleHeights are the downscale choices to offer besides "Original"
    // (e.g. {1080, 720}), matched by min(width, height) of the source.
    virtual void exportVideo(const QUrl &suggestedUrl, const QList<int> &scaleHeights) = 0;

signals:
    void openSelected(const QUrl &url);
    void videosSelected(const QList<QUrl> &urls);
    void cutListOpenSelected(const QUrl &url);
    void cutListSaveSelected(const QUrl &url);
    // scaleHeight is 0 for "Original", otherwise the chosen short-side size.
    void exportSelected(const QUrl &url, int scaleHeight);
    void failed(const QString &message);
};
