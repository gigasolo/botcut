#include "ffmpeg.h"

#include <QDir>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QStandardPaths>

namespace ffmpeg {

namespace {
// Upper bound on a synchronous probe so a hung/unresponsive file (e.g. a stalled
// network mount) can't freeze the caller — load() runs probe() on the UI thread.
constexpr int kProbeTimeoutMs = 15000;
// Poll granularity while waiting on a thumbnail child, so cancellation is prompt.
constexpr int kThumbPollMs = 50;

int jsonInt(const QJsonValue &value) {
    if (value.isDouble())
        return qRound(value.toDouble());
    bool ok = false;
    const int parsed = value.toString().toInt(&ok);
    return ok ? parsed : 0;
}

double jsonRate(const QJsonValue &value) {
    const QString text = value.toString().trimmed();
    if (text.isEmpty())
        return 0.0;
    const int slash = text.indexOf(QLatin1Char('/'));
    if (slash < 0) {
        bool ok = false;
        const double parsed = text.toDouble(&ok);
        return ok ? parsed : 0.0;
    }
    bool okNum = false;
    bool okDen = false;
    const double num = text.left(slash).toDouble(&okNum);
    const double den = text.mid(slash + 1).toDouble(&okDen);
    if (!okNum || !okDen || den == 0.0)
        return 0.0;
    return num / den;
}
}

QString toolPath(const QString &tool) {
    return QStandardPaths::findExecutable(tool);
}

VideoInfo probe(const QString &path) {
    VideoInfo info;
    info.path = path;

    const QString ffprobe = toolPath("ffprobe");
    if (ffprobe.isEmpty()) {
        info.error = "`ffprobe` was not found on your PATH. Install ffmpeg.";
        return info;
    }

    QProcess proc;
    proc.start(ffprobe, {
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    });
    if (!proc.waitForFinished(kProbeTimeoutMs)) {
        proc.kill();
        proc.waitForFinished(-1);
        info.error = "ffprobe timed out reading this file.";
        return info;
    }

    if (proc.exitStatus() != QProcess::NormalExit || proc.exitCode() != 0) {
        info.error = QString::fromUtf8(proc.readAllStandardError()).trimmed();
        if (info.error.isEmpty())
            info.error = "ffprobe failed.";
        return info;
    }

    const QJsonDocument doc = QJsonDocument::fromJson(proc.readAllStandardOutput());
    const QJsonObject root = doc.object();
    QJsonObject stream;
    for (const QJsonValue &value : root.value("streams").toArray()) {
        const QJsonObject candidate = value.toObject();
        const QString type = candidate.value("codec_type").toString();
        if (type == "video" && stream.isEmpty())
            stream = candidate;
        else if (type == "audio")
            info.audio = true;
    }
    if (stream.isEmpty()) {
        info.error = "No video stream found in this file.";
        return info;
    }

    info.width = stream.value("width").toInt();
    info.height = stream.value("height").toInt();
    info.frameRate = jsonRate(stream.value(QStringLiteral("avg_frame_rate")));
    if (info.frameRate <= 0.0)
        info.frameRate = jsonRate(stream.value(QStringLiteral("r_frame_rate")));
    info.rotation = jsonInt(stream.value(QStringLiteral("tags")).toObject().value(QStringLiteral("rotate")));
    for (const QJsonValue &side : stream.value(QStringLiteral("side_data_list")).toArray()) {
        const QJsonObject item = side.toObject();
        if (item.contains(QStringLiteral("rotation")))
            info.rotation = jsonInt(item.value(QStringLiteral("rotation")));
    }

    // Duration can live on the stream or on the container.
    QString durationStr = stream.value("duration").toString();
    if (durationStr.isEmpty())
        durationStr = root.value("format").toObject().value("duration").toString();
    if (durationStr.isEmpty()) {
        info.error = "Could not determine the video duration.";
        return info;
    }

    info.duration = durationStr.toDouble();

    info.ok = info.duration > 0.0;
    if (!info.ok)
        info.error = "Video has a zero or invalid duration.";
    return info;
}

QImage thumbnail(const QString &path, double time, int height,
                 const std::atomic<bool> *cancel) {
    const QString ffmpeg = toolPath("ffmpeg");
    if (ffmpeg.isEmpty())
        return {};

    QProcess proc;
    proc.start(ffmpeg, {
        "-loglevel", "error",
        "-ss", QString::number(qMax(time, 0.0), 'f', 3),
        "-i", path,
        "-frames:v", "1",
        "-vf", QString("scale=-1:%1").arg(height),
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1",
    });

    // Poll instead of waitForFinished(-1) so a cancel request can kill the child
    // promptly — otherwise the std::future destructor in ThumbWorker would block
    // the UI thread until ffmpeg finishes on its own.
    while (!proc.waitForFinished(kThumbPollMs)) {
        if (proc.state() == QProcess::NotRunning)
            break;  // failed to start, or exited between polls
        if (cancel && cancel->load(std::memory_order_relaxed)) {
            proc.kill();
            proc.waitForFinished(-1);
            return {};
        }
    }

    if (proc.exitStatus() != QProcess::NormalExit || proc.exitCode() != 0)
        return {};

    const QByteArray data = proc.readAllStandardOutput();
    QImage img;
    img.loadFromData(data, "JPEG");
    return img;
}

namespace {

bool displayRotated(int rotation) {
    return rotation % 360 != 0;
}

QSize fittedSize(int width, int height, int shortSide) {
    int outW = qMax(width, 2);
    int outH = qMax(height, 2);
    if (shortSide > 0 && width > 0 && height > 0) {
        if (width >= height) {
            outH = shortSide;
            outW = int((qint64(width) * shortSide) / height);
        } else {
            outW = shortSide;
            outH = int((qint64(height) * shortSide) / width);
        }
    }
    if (outW % 2)
        --outW;
    if (outH % 2)
        --outH;
    return QSize(qMax(outW, 2), qMax(outH, 2));
}

QString openedVaapiNode() {
    static bool probed = false;
    static QString found;
    if (probed)
        return found;
    probed = true;
    const QString ffmpegBin = toolPath(QStringLiteral("ffmpeg"));
    if (ffmpegBin.isEmpty())
        return {};
    const QDir dri(QStringLiteral("/dev/dri"));
    const QStringList names =
        dri.entryList(QDir::AllEntries | QDir::System | QDir::NoDotAndDotDot, QDir::Name);
    for (const QString &name : names) {
        if (!name.startsWith(QStringLiteral("renderD")))
            continue;
        const QString node = dri.absoluteFilePath(name);
        QProcess proc;
        proc.start(ffmpegBin, {
            QStringLiteral("-hide_banner"),
            QStringLiteral("-loglevel"),
            QStringLiteral("error"),
            QStringLiteral("-init_hw_device"),
            QStringLiteral("vaapi=va:") + node,
            QStringLiteral("-f"),
            QStringLiteral("lavfi"),
            QStringLiteral("-i"),
            QStringLiteral("color=c=black:s=16x16:d=0.1"),
            QStringLiteral("-frames:v"),
            QStringLiteral("1"),
            QStringLiteral("-f"),
            QStringLiteral("null"),
            QStringLiteral("-"),
        });
        if (!proc.waitForFinished(8000)) {
            proc.kill();
            proc.waitForFinished(1000);
            continue;
        }
        if (proc.exitStatus() == QProcess::NormalExit && proc.exitCode() == 0) {
            found = node;
            break;
        }
    }
    return found;
}

QStringList trimArgsOnVaapi(const QString &src, const QString &dst, const QList<edit::Range> &ranges,
                            bool audio, int scaleHeight, const QString &device, int frameWidth,
                            int frameHeight, int rotation, double frameRate) {
    QStringList args = {
        QStringLiteral("-y"),
        QStringLiteral("-loglevel"),
        QStringLiteral("error"),
        QStringLiteral("-progress"),
        QStringLiteral("pipe:1"),
        QStringLiteral("-init_hw_device"),
        QStringLiteral("vaapi=va:") + device,
        QStringLiteral("-filter_hw_device"),
        QStringLiteral("va"),
    };
    // A display matrix is applied on software decode. Hardware surfaces skip it.
    // Below 2 fps, VA-API hwaccel plus hwdownload segfaults in ffmpeg on this Arc.
    const bool hwDecode = !displayRotated(rotation) && !(frameRate > 0.0 && frameRate < 2.0);
    QStringList filters;
    for (int i = 0; i < ranges.size(); ++i) {
        if (hwDecode) {
            args << QStringLiteral("-hwaccel") << QStringLiteral("vaapi")
                 << QStringLiteral("-hwaccel_device") << device
                 << QStringLiteral("-hwaccel_output_format") << QStringLiteral("vaapi");
        }
        args << QStringLiteral("-ss") << QString::number(ranges[i].start, 'f', 3)
             << QStringLiteral("-t") << QString::number(qMax(ranges[i].length(), 0.0), 'f', 3)
             << QStringLiteral("-i") << src;
        if (!hwDecode)
            continue;
        // Download after the GPU scale. A second VA-API input left on the
        // device makes this Arc reject the surface during concat.
        if (scaleHeight > 0 && frameWidth > 0 && frameHeight > 0) {
            const QSize size = fittedSize(frameWidth, frameHeight, scaleHeight);
            filters << QStringLiteral("[%1:v:0]scale_vaapi=%2:%3:format=nv12:force_original_aspect_ratio=decrease,"
                                      "hwdownload,format=nv12,pad=%2:%3:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                                      "format=nv12,hwupload[v%1]")
                           .arg(i)
                           .arg(size.width())
                           .arg(size.height());
        } else {
            filters << QStringLiteral("[%1:v:0]scale_vaapi=format=nv12,hwdownload,format=nv12,setsar=1,"
                                      "format=nv12,hwupload[v%1]")
                           .arg(i);
        }
    }

    QString graph;
    if (hwDecode) {
        QString concatIn;
        for (int i = 0; i < ranges.size(); ++i) {
            concatIn += QStringLiteral("[v%1]").arg(i);
            if (audio)
                concatIn += QStringLiteral("[%1:a:0]").arg(i);
        }
        filters << concatIn
                        + QStringLiteral("concat=n=%1:v=1:a=%2[v]%3")
                              .arg(ranges.size())
                              .arg(audio ? 1 : 0)
                              .arg(audio ? QStringLiteral("[a]") : QString());
        graph = filters.join(QLatin1Char(';'));
    } else {
        QString concatIn;
        for (int i = 0; i < ranges.size(); ++i) {
            concatIn += QStringLiteral("[%1:v:0]").arg(i);
            if (audio)
                concatIn += QStringLiteral("[%1:a:0]").arg(i);
        }
        graph = concatIn + QStringLiteral("concat=n=%1:v=1:a=%2").arg(ranges.size()).arg(audio ? 1 : 0);
        if (scaleHeight > 0) {
            graph += QStringLiteral("[joined]%1;[joined]scale='if(gt(iw,ih),-2,%2)':'if(gt(iw,ih),%2,-2)',"
                                    "format=nv12,hwupload[v]")
                         .arg(audio ? QStringLiteral("[a]") : QString())
                         .arg(scaleHeight);
        } else {
            graph += QStringLiteral("[raw]%1;[raw]format=nv12,hwupload[v]")
                         .arg(audio ? QStringLiteral("[a]") : QString());
        }
    }

    args << QStringLiteral("-filter_complex") << graph << QStringLiteral("-map") << QStringLiteral("[v]");
    if (audio)
        args << QStringLiteral("-map") << QStringLiteral("[a]") << QStringLiteral("-c:a") << QStringLiteral("aac");
    args << QStringLiteral("-c:v") << QStringLiteral("h264_vaapi") << QStringLiteral("-qp") << QStringLiteral("20")
         << QStringLiteral("-movflags") << QStringLiteral("+faststart") << dst;
    return args;
}

}  // namespace

QString vaapiDevice(QString *error) {
    if (error)
        error->clear();
    const QString choice = QString::fromUtf8(qgetenv("BOTCUT_ENCODER")).trimmed().toLower();
    if (choice == QLatin1String("x264"))
        return {};
    if (!choice.isEmpty() && choice != QLatin1String("auto") && choice != QLatin1String("vaapi")) {
        if (error)
            *error = QStringLiteral("BOTCUT_ENCODER must be x264 or vaapi, not %1").arg(choice);
        return {};
    }
    const QString node = openedVaapiNode();
    if (node.isEmpty() && choice == QLatin1String("vaapi") && error)
        *error = QStringLiteral("BOTCUT_ENCODER=vaapi but no VA-API device opened");
    return node;
}

QStringList trimArgs(const QString &src, const QString &dst,
                     const QList<edit::Range> &ranges, bool audio, int scaleHeight,
                     const QString &vaapiDevice, int frameWidth, int frameHeight, int rotation,
                     double frameRate) {
    if (!vaapiDevice.isEmpty())
        return trimArgsOnVaapi(src, dst, ranges, audio, scaleHeight, vaapiDevice, frameWidth, frameHeight,
                               rotation, frameRate);
    // Machine-readable progress on stdout (errors stay on stderr), so the UI
    // can show how far along the encode is.
    QStringList args = {"-y", "-loglevel", "error", "-progress", "pipe:1"};
    // One input per range: -ss before -i seeks fast and -t bounds it, so only
    // what survives the cut is decoded. The concat filter joins them.
    QString graph;
    for (int i = 0; i < ranges.size(); ++i) {
        args << "-ss" << QString::number(ranges[i].start, 'f', 3)
             << "-t" << QString::number(qMax(ranges[i].length(), 0.0), 'f', 3)
             << "-i" << src;
        graph += QString("[%1:v:0]").arg(i) + (audio ? QString("[%1:a:0]").arg(i) : QString());
    }
    graph += QString("concat=n=%1:v=1:a=%2").arg(ranges.size()).arg(audio ? 1 : 0);
    // Cap the shorter side, judged on the decoded (rotation-applied) frame, so
    // portrait and landscape both keep their aspect ratio. -2 keeps the other
    // side divisible by two, which libx264 requires.
    if (scaleHeight > 0)
        graph += QString("[joined]%1;[joined]scale='if(gt(iw,ih),-2,%2)':'if(gt(iw,ih),%2,-2)'[v]")
                     .arg(audio ? "[a]" : "").arg(scaleHeight);
    else
        graph += QString("[v]") + (audio ? "[a]" : "");
    args << "-filter_complex" << graph << "-map" << "[v]";
    if (audio)
        args << "-map" << "[a]" << "-c:a" << "aac";
    // +faststart puts the moov atom up front so shared clips start playing
    // before they finish downloading.
    args << "-c:v" << "libx264" << "-preset" << "veryfast" << "-crf" << "18"
         << "-movflags" << "+faststart"
         << dst;
    return args;
}

}  // namespace ffmpeg
