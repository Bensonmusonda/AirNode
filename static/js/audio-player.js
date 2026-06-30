/**
 * AirNode Audio Player
 * Alpine.js component — function is attached to window automatically,
 * called via x-data="audioPlayerComponent()" in audio_player.html
 *
 * Handles:
 *  - Play/pause, seek, volume
 *  - Prev/next track navigation within current directory
 *  - Auto-advance on track end
 *  - Formatted time display
 */

function audioPlayerComponent() {
    return {
        // ── State ────────────────────────────────────────────────
        playing: false,
        loading: true,
        error: false,
        currentTime: 0,
        duration: 0,
        volume: 1,
        seeking: false,

        // ── Helpers ──────────────────────────────────────────────
        formatTime(secs) {
            if (!isFinite(secs) || secs < 0) return '0:00';
            const m = Math.floor(secs / 60);
            const s = Math.floor(secs % 60).toString().padStart(2, '0');
            return `${m}:${s}`;
        },

        get progressPercent() {
            if (!this.duration) return 0;
            return (this.currentTime / this.duration) * 100;
        },

        // ── Audio element control ───────────────────────────────
        get audioEl() {
            return this.$refs.audioEl;
        },

        togglePlay() {
            if (!this.audioEl) return;
            if (this.playing) {
                this.audioEl.pause();
            } else {
                this.audioEl.play().catch(() => { this.error = true; });
            }
        },

        onPlay() { this.playing = true; },
        onPause() { this.playing = false; },

        onLoadedMetadata() {
            this.duration = this.audioEl.duration || 0;
            this.loading = false;
        },

        onTimeUpdate() {
            if (!this.seeking) {
                this.currentTime = this.audioEl.currentTime;
            }
        },

        onEnded() {
            this.playing = false;
            // Auto-advance to next track
            const advanced = this.navigate(1, /*autoplay=*/ true);
            if (!advanced) {
                this.currentTime = 0;
            }
        },

        onError() {
            this.loading = false;
            this.error = true;
        },

        // ── Seeking ──────────────────────────────────────────────
        startSeek() {
            this.seeking = true;
        },

        seekTo(percent) {
            if (!this.duration) return;
            this.currentTime = (percent / 100) * this.duration;
        },

        commitSeek() {
            if (this.audioEl) {
                this.audioEl.currentTime = this.currentTime;
            }
            this.seeking = false;
        },

        onSeekInput(event) {
            this.seekTo(parseFloat(event.target.value));
        },

        // ── Volume ───────────────────────────────────────────────
        onVolumeInput(event) {
            this.volume = parseFloat(event.target.value);
            if (this.audioEl) this.audioEl.volume = this.volume;
        },

        // ── Track list / navigation (mirrors image viewer pattern) ─
        getAudioList() {
            const audioExts = ['mp3', 'ogg', 'wav', 'm4a', 'aac', 'flac'];
            return Array.from(document.querySelectorAll('.file-row'))
                .filter(row => audioExts.includes((row.dataset.ext || '').toLowerCase()))
                .map(row => ({
                    name: row.dataset.name,
                    path: row.dataset.path,
                }))
                .filter(item => item.path);
        },

        navigate(direction, autoplay = false) {
            const tracks = this.getAudioList();
            if (tracks.length < 2) return false;

            if (!window.__airnode || !window.__airnode.viewer) return false;
            const currentPath = window.__airnode.viewer.path;

            const idx = tracks.findIndex(t => t.path === currentPath);
            if (idx === -1) return false;

            const nextIdx = (idx + direction + tracks.length) % tracks.length;
            const next = tracks[nextIdx];

            window.__airnode.viewer = {
                name: next.name,
                path: next.path,
                kind: 'audio',
            };

            this.loading = true;
            this.error = false;
            this.currentTime = 0;
            this.duration = 0;

            if (autoplay) {
                // Wait for the new src to bind then play
                this.$nextTick(() => {
                    setTimeout(() => {
                        this.audioEl?.play().catch(() => {});
                    }, 50);
                });
            }

            return true;
        },

        // ── Lifecycle ────────────────────────────────────────────
        init() {
            this.loading = true;
            this.error = false;
            this.playing = false;
            this.currentTime = 0;
            this.duration = 0;

            this.$nextTick(() => {
                if (this.audioEl) {
                    this.audioEl.volume = this.volume;
                }
            });
        },
    };
}