#include "timeline.h"

#include <QHash>
#include <QVariantMap>

#include <algorithm>
#include <cmath>

QVariantList Timeline::clipList() const {
    QVariantList result;
    for (const edit::Range &clip : m_clips)
        result.append(QVariantMap{{QStringLiteral("start"), clip.start},
                                  {QStringLiteral("end"), clip.end}});
    return result;
}

bool Timeline::unexported() const {
    return !m_clips.isEmpty() && !edit::untouched(m_clips, m_duration)
        && m_clips != m_exported;
}

void Timeline::reset(double duration) {
    m_duration = std::max(0.0, duration);
    m_clips = m_duration > 0.0 ? edit::whole(m_duration) : edit::Clips{};
    m_exported.clear();
    m_undo.clear();
    m_redo.clear();
    m_gesture = false;
    emit changed();
}

void Timeline::load(double duration, const edit::Clips &clips) {
    reset(duration);
    if (!clips.isEmpty())
        apply(clips);
}

void Timeline::markExported(const edit::Clips &clips) {
    m_exported = clips;
    emit changed();
}

void Timeline::apply(edit::Clips next) {
    // Mid-drag, clips keep their indices; the gesture's end normalizes.
    if (!m_gesture)
        next = edit::normalized(next, m_duration);
    if (next == m_clips || next.isEmpty())
        return;
    if (!m_gesture || !m_gestureRecorded) {
        m_undo.append(m_clips);
        m_redo.clear();
        m_gestureRecorded = m_gesture;
    }
    m_clips = next;
    emit changed();
}

int Timeline::clipAt(double t) const {
    for (int i = 0; i < m_clips.size(); ++i) {
        if (t >= m_clips[i].start && t < m_clips[i].end)
            return i;
    }
    return -1;
}

int Timeline::gapAt(double t) const {
    int n = 0;
    while (n < m_clips.size() && m_clips[n].end <= t)
        ++n;
    return n;
}

double Timeline::playableFrom(double t) const {
    // A playhead within a frame or so of a clip's end has finished it.
    for (const edit::Range &clip : m_clips) {
        if (t < clip.end - 0.03)
            return std::max(t, clip.start);
    }
    return -1.0;
}

double Timeline::edgeFrom(double t, int direction) const {
    if (m_clips.isEmpty())
        return 0.0;
    double target = direction > 0 ? m_clips.last().end : m_clips.first().start;
    for (const edit::Range &clip : m_clips) {
        for (const double edge : {clip.start, clip.end}) {
            if (direction > 0 && edge > t + 0.01)
                return edge;
            if (direction < 0 && edge < t - 0.01)
                target = edge;
        }
    }
    return target;
}

void Timeline::split(double time) {
    for (int i = 0; i < m_clips.size(); ++i) {
        const edit::Range clip = m_clips[i];
        if (time - clip.start < edit::minimumClip || clip.end - time < edit::minimumClip)
            continue;
        edit::Clips next = m_clips;
        next[i].end = time;
        next.insert(i + 1, {time, clip.end});
        apply(next);
        return;
    }
}

void Timeline::setClip(int index, double start, double end) {
    if (index < 0 || index >= m_clips.size())
        return;
    // A clip can grow into a gap, never over its neighbours.
    const double low = index > 0 ? m_clips[index - 1].end : 0.0;
    const double high = index + 1 < m_clips.size() ? m_clips[index + 1].start : m_duration;
    start = std::clamp(start, low, high);
    end = std::clamp(end, low, high);
    if (end - start < edit::minimumClip)
        return;
    edit::Clips next = m_clips;
    next[index] = {start, end};
    apply(next);
}

void Timeline::moveEdge(int index, bool start, double t) {
    if (index < 0 || index >= m_clips.size())
        return;
    const edit::Range clip = m_clips[index];
    if (start)
        setClip(index, std::min(t, clip.end - edit::minimumClip), clip.end);
    else
        setClip(index, clip.start, std::max(t, clip.start + edit::minimumClip));
}

void Timeline::trimTo(double t, bool start) {
    int i = clipAt(t);
    if (i < 0)
        i = start ? gapAt(t) : gapAt(t) - 1;
    if (i < 0 || i >= m_clips.size())
        return;
    if (start)
        setClip(i, t, m_clips[i].end);
    else
        setClip(i, m_clips[i].start, t);
}

void Timeline::removeClip(int index) {
    if (index < 0 || index >= m_clips.size() || m_clips.size() < 2)
        return;
    edit::Clips next = m_clips;
    next.removeAt(index);
    apply(next);
}

void Timeline::removeOrRestoreAt(double t) {
    const int i = clipAt(t);
    if (i >= 0)
        removeClip(i);
    else
        restoreGap(gapAt(t));
}

void Timeline::restoreGap(int gap) {
    if (m_clips.isEmpty() || gap < 0 || gap > m_clips.size())
        return;
    if (gap == 0)
        setClip(0, 0.0, m_clips[0].end);
    else if (gap == m_clips.size())
        setClip(gap - 1, m_clips[gap - 1].start, m_duration);
    else
        joinClips(gap - 1);
}

void Timeline::joinClips(int index) {
    if (index < 0 || index + 1 >= m_clips.size())
        return;
    edit::Clips next = m_clips;
    next[index].end = next[index + 1].end;
    next.removeAt(index + 1);
    apply(next);
}

void Timeline::beginGesture() {
    if (m_clips.isEmpty())
        return;
    m_gesture = true;
    m_gestureRecorded = false;
}

void Timeline::endGesture() {
    if (!m_gesture)
        return;
    m_gesture = false;
    // Normalizing can drop a clip too short to keep; never let that empty the video.
    const edit::Clips next = edit::normalized(m_clips, m_duration);
    if (!next.isEmpty() && next != m_clips) {
        m_clips = next;
        emit changed();
    }
}

void Timeline::undo() {
    if (m_gesture || m_undo.isEmpty())
        return;
    m_redo.append(m_clips);
    m_clips = m_undo.takeLast();
    emit changed();
}

void Timeline::redo() {
    if (m_gesture || m_redo.isEmpty())
        return;
    m_undo.append(m_clips);
    m_clips = m_redo.takeLast();
    emit changed();
}

namespace {

bool sameEdge(const PlanFilm::Segment &a, const PlanFilm::Segment &b) {
    return a.origin == b.origin && a.start == b.start && a.end == b.end;
}

}

double PlanFilm::keptDuration() const {
    double total = 0;
    for (const Segment &seg : m_current)
        total += std::max(0.0, seg.end - seg.start);
    return total;
}

bool PlanFilm::unexported() const {
    if (!m_active)
        return false;
    if (m_current.size() != m_captured.size())
        return true;
    for (int i = 0; i < m_current.size(); ++i) {
        if (!sameEdge(m_current.at(i), m_captured.at(i)))
            return true;
    }
    return false;
}

QVariantList PlanFilm::clipList() const {
    QVariantList result;
    for (const View &view : m_view) {
        result.append(QVariantMap{{QStringLiteral("start"), view.start},
                                  {QStringLiteral("end"), view.end}});
    }
    return result;
}

QJsonArray PlanFilm::segmentsJson() const {
    QJsonArray out;
    for (const Segment &seg : m_current) {
        QJsonObject obj = seg.raw;
        obj.insert(QStringLiteral("clip"), seg.clip);
        obj.insert(QStringLiteral("start"), seg.start);
        obj.insert(QStringLiteral("end"), seg.end);
        if (!seg.reason.isEmpty())
            obj.insert(QStringLiteral("reason"), seg.reason);
        out.append(obj);
    }
    return out;
}

void PlanFilm::load(const QList<Segment> &segments) {
    m_gesture = false;
    m_gestureRecorded = false;
    m_undo.clear();
    m_redo.clear();
    m_anchor.clear();
    m_frozenView.clear();
    m_captured = segments;
    for (int i = 0; i < m_captured.size(); ++i)
        m_captured[i].origin = i;
    m_current = m_captured;
    m_active = !m_current.isEmpty();
    relayout();
    emit changed();
}

void PlanFilm::clear() {
    if (!m_active && m_current.isEmpty() && m_duration == 0)
        return;
    m_active = false;
    m_gesture = false;
    m_gestureRecorded = false;
    m_current.clear();
    m_captured.clear();
    m_view.clear();
    m_anchor.clear();
    m_frozenView.clear();
    m_undo.clear();
    m_redo.clear();
    m_duration = 0;
    emit changed();
}

void PlanFilm::takeUndo() {
    if (!m_gesture || !m_gestureRecorded) {
        m_undo.append(m_current);
        m_redo.clear();
        m_gestureRecorded = m_gesture;
    }
}

void PlanFilm::relayout() {
    m_view.clear();
    m_view.reserve(m_current.size());
    QHash<int, int> at;
    for (int i = 0; i < m_current.size(); ++i)
        at.insert(m_current.at(i).origin, i);
    QList<View> placed;
    placed.reserve(m_current.size());
    for (int i = 0; i < m_current.size(); ++i)
        placed.append(View{});
    double cursor = 0;
    for (int origin = 0; origin < m_captured.size(); ++origin) {
        const auto found = at.constFind(origin);
        if (found == at.cend()) {
            cursor += std::max(0.0, m_captured.at(origin).end - m_captured.at(origin).start);
            continue;
        }
        const int index = found.value();
        const double len = std::max(0.0, m_current.at(index).end - m_current.at(index).start);
        placed[index].start = cursor;
        placed[index].end = cursor + len;
        cursor += len;
    }
    // Segments are kept in captured order, so the placed list matches m_current.
    m_view = placed;
    m_duration = cursor;
}

void PlanFilm::applyEdge(int index, const Segment &updated) {
    if (index < 0 || index >= m_current.size())
        return;
    if (sameEdge(updated, m_current.at(index)) && updated.clip == m_current.at(index).clip)
        return;
    takeUndo();
    m_current[index] = updated;
    if (m_gesture && index < m_frozenView.size() && index < m_view.size() && index < m_anchor.size()) {
        const double len = std::max(0.0, updated.end - updated.start);
        if (updated.start != m_anchor.at(index).start && updated.end == m_anchor.at(index).end) {
            m_view[index].end = m_frozenView.at(index).end;
            m_view[index].start = m_frozenView.at(index).end - len;
        } else {
            m_view[index].start = m_frozenView.at(index).start;
            m_view[index].end = m_frozenView.at(index).start + len;
        }
    } else if (!m_gesture) {
        relayout();
    }
    emit changed();
    if (!m_gesture)
        emit committed();
}

int PlanFilm::clipAt(double t) const {
    for (int i = 0; i < m_view.size(); ++i) {
        if (t >= m_view.at(i).start && t < m_view.at(i).end)
            return i;
    }
    return -1;
}

int PlanFilm::gapAt(double t) const {
    int n = 0;
    while (n < m_view.size() && m_view.at(n).end <= t)
        ++n;
    return n;
}

double PlanFilm::playableFrom(double t) const {
    for (const View &view : m_view) {
        if (t < view.end - 0.03)
            return std::max(t, view.start);
    }
    return -1;
}

double PlanFilm::edgeFrom(double t, int direction) const {
    if (m_view.isEmpty())
        return 0;
    double target = direction > 0 ? m_view.last().end : m_view.first().start;
    for (const View &view : m_view) {
        for (const double edge : {view.start, view.end}) {
            if (direction > 0 && edge > t + 0.01)
                return edge;
            if (direction < 0 && edge < t - 0.01)
                target = edge;
        }
    }
    return target;
}

QVariantMap PlanFilm::sourceFor(int index, double sourceTime) const {
    if (index < 0 || index >= m_current.size() || index >= m_view.size())
        return {{QStringLiteral("ok"), false}};
    const Segment &seg = m_current.at(index);
    return {{QStringLiteral("ok"), true},
            {QStringLiteral("path"), seg.path},
            {QStringLiteral("source"), std::clamp(sourceTime, seg.start, seg.end)},
            {QStringLiteral("end"), seg.end},
            {QStringLiteral("index"), index}};
}

QVariantMap PlanFilm::sourceAt(double displayTime) const {
    // Half-open, so a shared boundary is the next block. The end window is only
    // for a scrub of the true end, which no block contains.
    int index = clipAt(displayTime);
    if (index < 0) {
        for (int i = 0; i < m_view.size(); ++i) {
            const double end = m_view.at(i).end;
            if (displayTime >= m_view.at(i).start && std::abs(displayTime - end) <= 0.001) {
                index = i;
                break;
            }
        }
    }
    if (index < 0 || index >= m_view.size() || index >= m_current.size())
        return {{QStringLiteral("ok"), false}};
    const double source = m_current.at(index).start + (displayTime - m_view.at(index).start);
    return sourceFor(index, source);
}

double PlanFilm::displayForSource(int index, double sourceTime) const {
    if (index < 0 || index >= m_current.size() || index >= m_view.size())
        return 0;
    return m_view.at(index).start + (sourceTime - m_current.at(index).start);
}

double PlanFilm::edgeTime(int index, bool startEdge) const {
    if (index < 0 || index >= m_current.size())
        return 0;
    return startEdge ? m_current.at(index).start : m_current.at(index).end;
}

double PlanFilm::playheadForEdge(int index, bool startEdge) const {
    if (index < 0 || index >= m_current.size() || index >= m_view.size())
        return 0;
    const double display = displayForSource(index, startEdge ? m_current.at(index).start
                                                              : m_current.at(index).end);
    if (startEdge)
        return display;
    // The packed out-point is the next block's start. Park strictly inside this one.
    const double inside = display - 0.001;
    return inside > m_view.at(index).start ? inside : m_view.at(index).start;
}

void PlanFilm::moveEdge(int index, bool startEdge, double t) {
    if (index < 0 || index >= m_current.size() || index >= m_view.size())
        return;
    const View view = (m_gesture && index < m_frozenView.size()) ? m_frozenView.at(index) : m_view.at(index);
    const Segment base = (m_gesture && index < m_anchor.size()) ? m_anchor.at(index) : m_current.at(index);
    const double room = std::max(edit::minimumClip, base.fileDuration);
    if (startEdge) {
        double length = std::clamp(view.end - t, edit::minimumClip, room);
        double start = base.end - length;
        if (start < 0)
            start = 0;
        if (base.end - start < edit::minimumClip)
            return;
        moveEdgeBy(index, true, start - base.start);
    } else {
        double length = std::clamp(t - view.start, edit::minimumClip, room);
        double end = base.start + length;
        if (end > base.fileDuration)
            end = base.fileDuration;
        if (end - base.start < edit::minimumClip)
            return;
        moveEdgeBy(index, false, end - base.end);
    }
}

void PlanFilm::moveEdgeBy(int index, bool startEdge, double delta) {
    if (!m_active || index < 0 || index >= m_current.size())
        return;
    const Segment base = (m_gesture && index < m_anchor.size()) ? m_anchor.at(index) : m_current.at(index);
    Segment updated = m_current.at(index);
    if (startEdge) {
        const double limit = base.end - edit::minimumClip;
        if (limit < 0)
            return;
        const double start = std::clamp(base.start + delta, 0.0, limit);
        if (base.end - start < edit::minimumClip)
            return;
        updated.start = start;
        updated.end = base.end;
    } else {
        const double ceiling = std::max(base.fileDuration, base.start + edit::minimumClip);
        const double floor = base.start + edit::minimumClip;
        if (ceiling < floor)
            return;
        const double end = std::clamp(base.end + delta, floor, ceiling);
        if (end - base.start < edit::minimumClip)
            return;
        updated.start = base.start;
        updated.end = end;
    }
    applyEdge(index, updated);
}

void PlanFilm::trimTo(double t, bool startEdge) {
    const int index = clipAt(t);
    if (index < 0)
        return;
    moveEdge(index, startEdge, t);
}

void PlanFilm::removeClip(int index) {
    if (m_gesture || index < 0 || index >= m_current.size() || m_current.size() < 2)
        return;
    takeUndo();
    m_current.removeAt(index);
    relayout();
    emit changed();
    emit committed();
}

void PlanFilm::removeOrRestoreAt(double t) {
    const int index = clipAt(t);
    if (index >= 0)
        removeClip(index);
    else
        restoreGap(gapAt(t));
}

void PlanFilm::restoreGap(int gap) {
    if (m_gesture || gap < 0 || m_captured.isEmpty() || m_current.isEmpty())
        return;
    QList<int> have;
    have.reserve(m_current.size());
    for (const Segment &seg : m_current)
        have.append(seg.origin);
    if (gap > have.size())
        return;
    const int before = gap == 0 ? -1 : have.at(gap - 1);
    const int after = gap >= have.size() ? m_captured.size() : have.at(gap);
    QList<Segment> next = m_current;
    int insertAt = gap;
    bool any = false;
    for (int origin = 0; origin < m_captured.size(); ++origin) {
        if (have.contains(origin) || origin <= before || origin >= after)
            continue;
        next.insert(insertAt, m_captured.at(origin));
        ++insertAt;
        any = true;
    }
    if (!any)
        return;
    takeUndo();
    m_current = next;
    relayout();
    emit changed();
    emit committed();
}

void PlanFilm::beginGesture() {
    if (m_current.isEmpty())
        return;
    m_gesture = true;
    m_gestureRecorded = false;
    m_anchor = m_current;
    m_frozenView = m_view;
}

void PlanFilm::endGesture() {
    if (!m_gesture)
        return;
    const bool edited = m_gestureRecorded;
    m_gesture = false;
    m_gestureRecorded = false;
    m_anchor.clear();
    m_frozenView.clear();
    relayout();
    emit changed();
    if (edited)
        emit committed();
}

void PlanFilm::undo() {
    if (m_gesture || m_undo.isEmpty())
        return;
    m_redo.append(m_current);
    m_current = m_undo.takeLast();
    relayout();
    emit changed();
    emit committed();
}

void PlanFilm::redo() {
    if (m_gesture || m_redo.isEmpty())
        return;
    m_undo.append(m_current);
    m_current = m_redo.takeLast();
    relayout();
    emit changed();
    emit committed();
}
