.pragma library

// mm:ss.cc, shared by Main.qml and TrimBar.qml. Rounds to centiseconds first so
// boundary values render correctly (e.g. 59.999 -> "01:00.00", not "00:60.00").
function fmt(sec) {
    if (sec < 0 || isNaN(sec))
        sec = 0;
    var cs = Math.round(sec * 100);
    var m = Math.floor(cs / 6000);
    var s = (cs - m * 6000) / 100;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s.toFixed(2);
}

// True once playback has reached the end of a line. A position still before
// the line has not arrived there yet.
function linePlayReachedEnd(position, start, end, playing) {
    if (!playing || start < 0 || end < start)
        return false;
    if (position < start)
        return false;
    return position >= end;
}

// Air after this kept line, and the next kept line's index. Null when
// nothing follows, so the caller stops instead of playing trailing air.
function nextKeptAir(lines, index, paceSec) {
    if (!lines || index < 0 || index >= lines.length)
        return null;
    var current = lines[index];
    // A missing keep is kept, same as the row.
    if (!current || current.keep === false)
        return null;
    var end = Number(current.end);
    var clip = Number(current.clip);
    if (!isFinite(Number(current.start)) || !isFinite(end))
        return null;
    var pace = Number(paceSec);
    for (var i = index + 1; i < lines.length; ++i) {
        var line = lines[i];
        if (!line || line.keep === false)
            continue;
        var start = Number(line.start);
        if (!isFinite(start) || !isFinite(Number(line.end)))
            continue;
        var air = 0;
        if (Number(line.clip) === clip) {
            var gap = start - end;
            if (gap > 0)
                air = Math.min(gap, pace);
        }
        return { air: air, next: i };
    }
    return null;
}
