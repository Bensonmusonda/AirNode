/**
 * AirNode Enhanced Cinema Video Player Component
 * Handles:
 * - Watch State Persistence & Resume Prompt
 * - Binge Mode ("Up Next" 5s countdown at 90% completion)
 * - Mobile Touch Gestures (Double-tap ±10s seek, Vertical swipe brightness/volume)
 * - Subtitle Offset Sync (-2.5s to +2.5s delay slider) & High-Contrast Toggle
 * - Aspect Ratio Switcher & Picture-in-Picture (PiP)
 */

function cinemaPlayerComponent() {
    return {
        videoPath: '',
        videoName: '',
        nextEpisode: null,
        
        // Player state
        playing: false,
        currentTime: 0,
        duration: 0,
        volume: 1,
        isMuted: false,
        aspectRatio: 'contain', // 'contain' | 'cover' | 'fill'
        
        // Resume prompt state
        savedState: null,
        showResumePrompt: false,

        // Binge mode state
        bingeActive: false,
        bingeCountdown: 5,
        bingeTimer: null,

        // Gestures state
        lastTap: 0,
        rippleText: '',
        showRipple: false,
        touchStartY: 0,
        brightness: 1,
        swipeType: null, // 'brightness' | 'volume'
        showSwipeIndicator: false,
        swipeIndicatorText: '',

        // Subtitles state
        subtitleOffset: 0,
        highContrastSubtitles: true,
        availableSubtitles: false,

        get videoEl() {
            return this.$refs.videoEl;
        },

        initPlayer(path, name, nextEp = null) {
            this.videoPath = path;
            this.videoName = name;
            this.nextEpisode = nextEp;
            this.showResumePrompt = false;
            this.bingeActive = false;
            this.subtitleOffset = 0;

            // Fetch watch state from backend
            fetch('/api/media/watch-state')
                .then(r => r.json())
                .then(states => {
                    if (states[path] && states[path].currentTime > 10 && !states[path].completed) {
                        this.savedState = states[path];
                        this.showResumePrompt = true;
                    }
                }).catch(() => {});
        },

        onPlay() {
            this.playing = true;
            if (window.AirNodePlayer && this.videoEl) {
                window.AirNodePlayer.playMedia(this.videoEl, {
                    title: this.videoName || 'Video Stream',
                    path: this.videoPath
                }, 'video');
            }
            this.saveProgressInterval();
        },

        onPause() {
            this.playing = false;
            this.saveWatchProgress();
        },

        onTimeUpdate() {
            if (!this.videoEl) return;
            this.currentTime = this.videoEl.currentTime;
            this.duration = this.videoEl.duration || 0;

            // Binge Mode Trigger at 90% completion
            if (this.duration > 0 && (this.currentTime / this.duration) >= 0.90 && this.nextEpisode && !this.bingeActive) {
                this.triggerBingeCountdown();
            }
        },

        resumePlayback() {
            if (this.savedState && this.videoEl) {
                this.videoEl.currentTime = this.savedState.currentTime;
            }
            this.showResumePrompt = false;
            this.videoEl?.play().catch(() => {});
        },

        startFromBeginning() {
            if (this.videoEl) {
                this.videoEl.currentTime = 0;
            }
            this.showResumePrompt = false;
            this.videoEl?.play().catch(() => {});
        },

        saveWatchProgress() {
            if (!this.videoPath || !this.videoEl) return;
            fetch('/api/media/watch-state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: this.videoPath,
                    currentTime: this.videoEl.currentTime,
                    duration: this.videoEl.duration || 0
                })
            }).catch(() => {});
        },

        saveProgressInterval() {
            if (this._saveTimer) clearInterval(this._saveTimer);
            this._saveTimer = setInterval(() => {
                if (this.playing) this.saveWatchProgress();
            }, 5000);
        },

        // Binge Mode
        triggerBingeCountdown() {
            this.bingeActive = true;
            this.bingeCountdown = 5;
            if (this.bingeTimer) clearInterval(this.bingeTimer);

            this.bingeTimer = setInterval(() => {
                this.bingeCountdown--;
                if (this.bingeCountdown <= 0) {
                    clearInterval(this.bingeTimer);
                    this.playNextEpisodeNow();
                }
            }, 1000);
        },

        cancelBinge() {
            this.bingeActive = false;
            if (this.bingeTimer) clearInterval(this.bingeTimer);
        },

        playNextEpisodeNow() {
            this.cancelBinge();
            if (this.nextEpisode && window.__airnode) {
                window.__airnode.openViewer({
                    name: this.nextEpisode.name || this.nextEpisode.title,
                    path: this.nextEpisode.path,
                    ext: this.nextEpisode.ext || 'mp4'
                });
            }
        },

        // Mobile Touch Gestures (Double-tap ±10s)
        handleTouchStart(e) {
            if (e.touches.length !== 1) return;
            const touch = e.touches[0];
            const now = Date.now();
            const width = e.currentTarget.clientWidth;
            const tapX = touch.clientX;

            this.touchStartY = touch.clientY;
            this.swipeType = tapX < width / 2 ? 'brightness' : 'volume';

            // Double tap check (< 300ms)
            if (now - this.lastTap < 300) {
                e.preventDefault();
                if (tapX > width / 2) {
                    this.seekRelative(10);
                    this.triggerRipple('+10s');
                } else {
                    this.seekRelative(-10);
                    this.triggerRipple('-10s');
                }
                this.lastTap = 0;
            } else {
                this.lastTap = now;
            }
        },

        handleTouchMove(e) {
            if (!this.touchStartY || e.touches.length !== 1) return;
            const deltaY = this.touchStartY - e.touches[0].clientY;

            if (Math.abs(deltaY) > 20) {
                if (this.swipeType === 'brightness') {
                    this.brightness = Math.max(0.3, Math.min(1.5, this.brightness + (deltaY > 0 ? 0.03 : -0.03)));
                    this.showSwipeIndicator = true;
                    this.swipeIndicatorText = `Brightness: ${Math.round(this.brightness * 100)}%`;
                } else if (this.swipeType === 'volume' && this.videoEl) {
                    this.volume = Math.max(0, Math.min(1, this.volume + (deltaY > 0 ? 0.03 : -0.03)));
                    this.videoEl.volume = this.volume;
                    this.showSwipeIndicator = true;
                    this.swipeIndicatorText = `Volume: ${Math.round(this.volume * 100)}%`;
                }
                this.touchStartY = e.touches[0].clientY;
            }
        },

        handleTouchEnd() {
            this.touchStartY = 0;
            setTimeout(() => { this.showSwipeIndicator = false; }, 1000);
        },

        triggerRipple(text) {
            this.rippleText = text;
            this.showRipple = true;
            setTimeout(() => { this.showRipple = false; }, 600);
        },

        seekRelative(secs) {
            if (this.videoEl) {
                this.videoEl.currentTime = Math.max(0, Math.min(this.videoEl.duration || 0, this.videoEl.currentTime + secs));
            }
        },

        // Aspect Ratio Toggle
        toggleAspectRatio() {
            const ratios = ['contain', 'cover', 'fill'];
            const idx = ratios.indexOf(this.aspectRatio);
            this.aspectRatio = ratios[(idx + 1) % ratios.length];
        },

        // Picture in Picture
        togglePiP() {
            if (document.pictureInPictureElement) {
                document.exitPictureInPicture().catch(() => {});
            } else if (this.videoEl && this.videoEl.requestPictureInPicture) {
                this.videoEl.requestPictureInPicture().catch(() => {});
            }
        },

        // Subtitle Offset Adjustment
        applySubtitleOffset() {
            if (!this.videoEl || !this.videoEl.textTracks) return;
            const tracks = this.videoEl.textTracks;
            const offset = parseFloat(this.subtitleOffset);

            for (let i = 0; i < tracks.length; i++) {
                const track = tracks[i];
                if (track.cues) {
                    for (let j = 0; j < track.cues.length; j++) {
                        const cue = track.cues[j];
                        if (cue._origStart === undefined) {
                            cue._origStart = cue.startTime;
                            cue._origEnd = cue.endTime;
                        }
                        cue.startTime = Math.max(0, cue._origStart + offset);
                        cue.endTime = Math.max(0, cue._origEnd + offset);
                    }
                }
            }
        }
    };
}

window.cinemaPlayerComponent = cinemaPlayerComponent;
