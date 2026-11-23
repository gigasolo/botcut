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
    // The line that opens the movie plays first, away from its place. What follows
    // it is the first kept line, and its place is passed over later.
    var from = current.hook === true ? 0 : index + 1;
    for (var i = from; i < lines.length; ++i) {
        var line = lines[i];
        if (!line || line.keep === false || line.hook === true)
            continue;
        var start = Number(line.start);
        if (!isFinite(start) || !isFinite(Number(line.end)))
            continue;
        var air = 0;
        if (current.hook !== true && Number(line.clip) === clip) {
            var gap = start - end;
            if (gap > 0)
                air = Math.min(gap, pace);
        }
        return { air: air, next: i };
    }
    return null;
}

// Air kept after a line before the next kept one, the way the chain plays it.
function airAfter(lines, index, paceSec) {
    var jump = nextKeptAir(lines, index, paceSec);
    return jump && isFinite(Number(jump.air)) ? Math.max(0, Number(jump.air)) : 0;
}

// The B-roll picture under the playhead on the line at `index`, or null. A
// cover is a run from its first line through its last; the footage plays on
// from the run's start across those lines. `src` is the time in the B-roll
// file to show now, `until` where on this line it ends. An older cover with
// no run stays inside its one line for up to four seconds.
function coverAt(lines, index, covers, clipPaths, posSec, paceSec) {
    if (!lines || index < 0 || index >= lines.length || !covers || !clipPaths)
        return null;
    var line = lines[index];
    if (!line || line.keep === false)
        return null;
    var start = Number(line.start);
    var end = Number(line.end);
    var pos = Number(posSec);
    if (!isFinite(start) || !isFinite(end) || !isFinite(pos))
        return null;
    var positions = {};
    for (var p = 0; p < lines.length; ++p) {
        if (lines[p] && lines[p].id !== undefined)
            positions[Number(lines[p].id)] = p;
    }
    for (var i = 0; i < covers.length; ++i) {
        var cover = covers[i];
        if (!cover)
            continue;
        var first = positions[Number(cover.line)];
        if (first === undefined)
            continue;
        var legacy = cover.through === undefined || cover.through === null;
        var last = legacy ? first : positions[Number(cover.through)];
        if (last === undefined || last < first)
            last = first;
        if (index < first || index > last)
            continue;
        var clip = Number(cover.clip);
        if (!isFinite(clip) || clip < 0 || clip >= clipPaths.length)
            return null;
        var from = Number(cover.start);
        if (!isFinite(from) || from < 0)
            from = 0;
        var to = Number(cover.end);
        var span = isFinite(to) && to > from ? to - from : (legacy ? 4.0 : 0);
        if (legacy)
            span = Math.min(span, 4.0);
        // How far into the run this line begins: the kept lines before it and their air.
        var offset = 0;
        for (var k = first; k < index; ++k) {
            var earlier = lines[k];
            if (!earlier || earlier.keep === false)
                return null;
            var s = Number(earlier.start), e = Number(earlier.end);
            if (!isFinite(s) || !isFinite(e))
                return null;
            offset += Math.max(0, e - s) + airAfter(lines, k, paceSec);
        }
        var left = span - offset;
        if (left <= 0)
            return null;
        var until = Math.min(end, start + left);
        if (pos < start || pos >= until)
            return null;
        return { path: String(clipPaths[clip] || ""), src: from + offset + (pos - start), until: until };
    }
    return null;
}
