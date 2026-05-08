/**
 * Timezone display helpers for MediaVortex.
 *
 * Storage convention: every datetime in the DB is UTC. The Flask
 * UtcJsonProvider serializes them as ISO-8601 with the explicit `Z`
 * suffix (e.g. "2026-05-08T22:11:19.123456Z"). This module converts
 * those strings into the user's configured display timezone for the UI.
 *
 * Display timezone source: window.MV_TIMEZONE (set by Base.html from
 * SystemSettings.DisplayTimezone). Falls back to "UTC" if missing.
 *
 * Usage:
 *
 *   1. Static markup in Jinja templates:
 *
 *      <span class="js-tz" data-utc="{{ value.isoformat() }}Z" data-fmt="full">
 *        {{ value.strftime('%Y-%m-%d %H:%M') }} UTC
 *      </span>
 *
 *      The text inside is the UTC fallback shown if JS fails. On
 *      DOMContentLoaded, this script rewrites it to the configured TZ.
 *
 *   2. Dynamic content built via AJAX:
 *
 *      const display = formatTime(row.AttemptDate, 'full');
 *      const ageDisplay = formatRelative(row.AttemptDate);
 *
 *   3. Re-applying after AJAX inserts new `.js-tz` nodes:
 *
 *      applyTimezoneSweep(document.getElementById('NewlyInsertedContainer'));
 *
 * Format names ("full", "datetime", "date", "time", "short") map to
 * Intl.DateTimeFormat option presets. Unknown names fall back to "full".
 */
(function () {
    'use strict';

    const TZ = (typeof window !== 'undefined' && window.MV_TIMEZONE) || 'UTC';

    const FORMATS = {
        full: { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: TZ },
        datetime: { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ },
        date: { year: 'numeric', month: 'short', day: '2-digit', timeZone: TZ },
        time: { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: TZ },
        short: { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ }
    };

    /**
     * Format a UTC ISO-8601 string into the configured display timezone.
     * @param {string|Date|null} utcInput The UTC ISO string or Date object.
     * @param {string} fmt One of 'full', 'datetime', 'date', 'time', 'short'.
     * @returns {string} Formatted timestamp, or '' if input is falsy/invalid.
     */
    function formatTime(utcInput, fmt) {
        if (!utcInput) return '';
        const date = (utcInput instanceof Date) ? utcInput : new Date(utcInput);
        if (isNaN(date.getTime())) return '';
        const opts = FORMATS[fmt] || FORMATS.full;
        try {
            return new Intl.DateTimeFormat([], opts).format(date);
        } catch (e) {
            // Fallback if browser doesn't recognize the IANA TZ name
            return date.toISOString();
        }
    }

    /**
     * Format a UTC timestamp as a relative duration ("2m ago", "5h ago", "3d ago").
     * For ages > 30 days, falls back to absolute date.
     */
    function formatRelative(utcInput) {
        if (!utcInput) return '';
        const date = (utcInput instanceof Date) ? utcInput : new Date(utcInput);
        if (isNaN(date.getTime())) return '';
        const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
        if (seconds < 0) return formatTime(date, 'short') + ' (future)';
        if (seconds < 60) return seconds + 's ago';
        if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
        if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
        if (seconds < 86400 * 30) return Math.floor(seconds / 86400) + 'd ago';
        return formatTime(date, 'date');
    }

    /**
     * Sweep a DOM subtree, rewriting every `.js-tz` element's text content
     * from `data-utc` (UTC ISO) into the display timezone.
     * Pass document or a specific container after AJAX inserts new nodes.
     */
    function applyTimezoneSweep(root) {
        const scope = root || document;
        const elements = scope.querySelectorAll('.js-tz');
        elements.forEach(function (el) {
            const utc = el.getAttribute('data-utc');
            if (!utc) return;
            const fmt = el.getAttribute('data-fmt') || 'full';
            if (fmt === 'relative') {
                el.textContent = formatRelative(utc);
            } else {
                el.textContent = formatTime(utc, fmt);
            }
            // Set a tooltip with the full UTC value for ops/troubleshooting clarity
            if (!el.title) {
                el.title = utc + ' (UTC)';
            }
        });
    }

    /**
     * Live clock for the navbar. Updates the #NavClockText element every
     * second with the current time formatted in the configured TZ. Includes
     * a short TZ abbreviation so the operator can see at a glance which zone
     * they are in. Self-corrects to the next whole second after the first
     * tick to avoid drift.
     */
    function startNavClock() {
        const target = document.getElementById('NavClockText');
        if (!target) return;

        const fmt = new Intl.DateTimeFormat([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZone: TZ,
            timeZoneName: 'short'
        });

        function tick() {
            try {
                target.textContent = fmt.format(new Date());
            } catch (e) {
                target.textContent = new Date().toISOString();
            }
        }
        tick();

        // Align next tick to the next whole second so the display flips
        // exactly on second boundaries instead of drifting.
        const msToNextSecond = 1000 - (Date.now() % 1000);
        setTimeout(function() {
            tick();
            setInterval(tick, 1000);
        }, msToNextSecond);
    }

    // Expose helpers globally for inline scripts and other JS modules
    window.formatTime = formatTime;
    window.formatRelative = formatRelative;
    window.applyTimezoneSweep = applyTimezoneSweep;
    window.startNavClock = startNavClock;

    // Auto-sweep + start nav clock on initial page load
    function onReady() {
        applyTimezoneSweep();
        startNavClock();
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }
})();
