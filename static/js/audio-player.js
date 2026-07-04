/**
 * AirNode Audio Player
 * Alpine.js component — function is attached to window automatically,
 * called via x-data="audioPlayerComponent()" in audio_player.html
 *
 * Handles:
 * - Play/pause, seek, volume
 * - Prev/next track navigation within current directory
 * - Auto-advance on track end
 * - Formatted time display
 * - Real-time rhythm/bass pulse tracking via Web Audio API
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

        // ── Audio Analyzer State ─────────────────────────────────
        audioCtx: null,
        analyser: null,
        dataArray: null,

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

            // Initialize context on first user interaction interaction
            this.initAudioAnalyzer();

            // Resume audio hardware context if suspended by browser security policy
            if (this.audioCtx && this.audioCtx.state === 'suspended') {
                this.audioCtx.resume();
            }

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

        // ── Web Audio Rhythm Analyzer ────────────────────────────
        initAudioAnalyzer() {
            if (this.audioCtx) return; // Prevent creating multiple nodes on the same audio tag

            try {
                const AudioContextClass = window.AudioContext || window.webkitAudioContext;
                this.audioCtx = new AudioContextClass();
                
                // Low fftSize means wider frequency bins—ideal for processing general rhythm/bass
                this.analyser = this.audioCtx.createAnalyser();
                this.analyser.fftSize = 64; 
                
                // Route element through analyzer node down to system output
                const source = this.audioCtx.createMediaElementSource(this.audioEl);
                source.connect(this.analyser);
                this.analyser.connect(this.audioCtx.destination);

                this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
                
                // Start animation loop
                this.animatePulse();
            } catch (e) {
                console.warn("Web Audio API could not initialize:", e);
            }
        },

        animatePulse() {
            if (this.playing && this.analyser && this.dataArray) {
                this.analyser.getByteFrequencyData(this.dataArray);

                // Isolate low frequencies (index 0, 1, 2 capture deep sub-bass and kick drums)
                const bassSum = this.dataArray[0] + this.dataArray[1] + this.dataArray[2];
                const bassAverage = bassSum / 3;

                // Normalize scale mapping (ranges neatly from 1.0 up to 1.10)
                const scale = 1 + (bassAverage / 255) * 0.10;

                if (this.$refs.audioArt) {
                    this.$refs.audioArt.style.transform = `scale(${scale})`;
                }
            } else if (!this.playing && this.$refs.audioArt) {
                // Return smoothly to normal bounds when song ends or pauses
                this.$refs.audioArt.style.transform = 'scale(1)';
            }

            requestAnimationFrame(() => this.animatePulse());
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

                if (window.lucide) {
                    window.lucide.createIcons();
                }
            });
        },
    };
}

// Bind to window for global Alpine access
window.audioPlayerComponent = audioPlayerComponent;