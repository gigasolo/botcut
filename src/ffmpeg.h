#pragma once

#include <QImage>
#include <QString>
#include <QStringList>

#include <atomic>

#include "edit.h"

// Thin wrappers around the ffmpeg/ffprobe command-line tools.
namespace ffmpeg {

struct VideoInfo {
    QString path;
    double duration = 0.0;  // seconds
    int width = 0;
    int height = 0;
    int rotation = 0;  // degrees from the display matrix, 0 when the frame is upright
    double frameRate = 0.0;  // frames per second, 0 when the file does not say
    bool audio = false;
    bool ok = false;
    QString error;
};

// Probe a file for a usable video stream and duration (runs ffprobe).
VideoInfo probe(const QString &path);

// Grab a single frame at `time` seconds, scaled to `height` px.
// Returns a null QImage on failure. If `cancel` is set and flips to true while
// the ffmpeg child is running, the child is killed and a null QImage returned.
QImage thumbnail(const QString &path, double time, int height = 90,
                 const std::atomic<bool> *cancel = nullptr);

// Build the ffmpeg argument list that writes the ranges of src, back to back,
// to dst. Cuts are frame-accurate and re-encoded with libx264/aac. A non-zero
// scaleHeight downscales so the shorter side becomes scaleHeight (1080p of a
// portrait video is 1080 wide), always preserving the aspect ratio.
// A non-empty vaapiDevice encodes with h264_vaapi on that render node instead.
// frameWidth/frameHeight size a GPU downscale. A non-zero rotation keeps
// decode on the CPU so ffmpeg can autorotate, then uploads for the encode.
// A frame rate below 2 does the same: VA-API hwaccel download segfaults on
// this Arc at 1 fps. 0 means the rate is unknown and hardware decode stays on.
QStringList trimArgs(const QString &src, const QString &dst,
                     const QList<edit::Range> &ranges, bool audio, int scaleHeight = 0,
                     const QString &vaapiDevice = QString(), int frameWidth = 0,
                     int frameHeight = 0, int rotation = 0, double frameRate = 0.0);

// Render node for an Arc encode, or empty when the CPU encoder should be used.
// BOTCUT_ENCODER=x264 skips the GPU. BOTCUT_ENCODER=vaapi sets *error when no
// device opens. Unset uses the first node that opens.
QString vaapiDevice(QString *error = nullptr);

// Locate a tool on PATH; returns empty string if missing.
QString toolPath(const QString &tool);

}  // namespace ffmpeg
