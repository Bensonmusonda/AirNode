/**
 * AirNode Global Media Manager Singleton (`window.AirNodePlayer`)
 * Enforces single-active-media playback across the entire application,
 * manages persistent mini-player state, and syncs with lock-screen MediaSession API.
 */

class AirNodeMediaManager {
    constructor() {
        this.activeMedia = null; // Currently active <audio> or <video> element
        this.mediaType = null;   // 'audio' | 'video'
        this.currentTrack = null;// { title, artist, album, path, cover, duration, currentTime }
        this.isPlaying = false;
        this.volume = 1.0;
        this.isMuted = false;
        this.queue = [];
        this.queueIndex = -1;
        this.listeners = new Set();
        this.sleepTimerId = null;
        this.sleepTimerEndTime = null;

        // Auto-bind media session actions
        this.setupMediaSession();
    }

    /**
     * Stops all active media elements playing in the DOM to prevent overlapping sound/video.
     */
    stopAll() {
        // Pause all audio and video tags on the page
        const allMedia = document.querySelectorAll('audio, video');
        allMedia.forEach(el => {
            try {
                if (!el.paused) {
                    el.pause();
                }
            } catch (e) {}
        });

        if (this.activeMedia) {
            try {
                this.activeMedia.pause();
            } catch (e) {}
            this.activeMedia = null;
        }

        this.isPlaying = false;
        this.notifyListeners();
    }

    /**
     * Registers and starts playback for a media element (audio or video).
     * Automatically calls `stopAll()` before initiating new playback.
     */
    playMedia(mediaEl, metadata = {}, mediaType = 'audio') {
        if (!mediaEl) return;

        // 1. Enforce single playback predictability: stop all other media first
        if (this.activeMedia !== mediaEl) {
            this.stopAll();
        }

        this.activeMedia = mediaEl;
        this.mediaType = mediaType;
        this.currentTrack = {
            title: metadata.title || metadata.name || 'Unknown Track',
            artist: metadata.artist || 'AirNode Media',
            album: metadata.album || 'AirNode Library',
            path: metadata.path || '',
            cover: metadata.cover || null,
            duration: mediaEl.duration || metadata.duration || 0,
            currentTime: mediaEl.currentTime || 0
        };

        // Event listeners on the media element
        mediaEl.onplay = () => {
            this.isPlaying = true;
            this.updateMediaSession();
            this.notifyListeners();
        };

        mediaEl.onpause = () => {
            this.isPlaying = false;
            this.notifyListeners();
        };

        mediaEl.ontimeupdate = () => {
            if (this.currentTrack) {
                this.currentTrack.currentTime = mediaEl.currentTime;
                this.currentTrack.duration = mediaEl.duration || this.currentTrack.duration;
            }
            this.notifyListeners();
        };

        mediaEl.onended = () => {
            this.isPlaying = false;
            this.notifyListeners();
            if (typeof metadata.onEnded === 'function') {
                metadata.onEnded();
            } else {
                this.playNextInQueue();
            }
        };

        // Start playback
        mediaEl.volume = this.isMuted ? 0 : this.volume;
        mediaEl.play().then(() => {
            this.isPlaying = true;
            this.updateMediaSession();
            this.notifyListeners();
        }).catch(err => {
            console.warn('[AirNodePlayer] Autoplay prevented or error:', err);
        });
    }

    togglePlayPause() {
        if (!this.activeMedia) return;
        if (this.isPlaying) {
            this.activeMedia.pause();
        } else {
            this.activeMedia.play().catch(() => {});
        }
    }

    seekTo(seconds) {
        if (this.activeMedia && isFinite(seconds)) {
            this.activeMedia.currentTime = Math.max(0, Math.min(seconds, this.activeMedia.duration || seconds));
            if (this.currentTrack) {
                this.currentTrack.currentTime = this.activeMedia.currentTime;
            }
            this.notifyListeners();
        }
    }

    setVolume(val) {
        this.volume = Math.max(0, Math.min(1, val));
        this.isMuted = this.volume === 0;
        if (this.activeMedia) {
            this.activeMedia.volume = this.volume;
        }
        this.notifyListeners();
    }

    toggleMute() {
        this.isMuted = !this.isMuted;
        if (this.activeMedia) {
            this.activeMedia.volume = this.isMuted ? 0 : this.volume;
        }
        this.notifyListeners();
    }

    // Queue management
    setQueue(trackList, startIndex = 0) {
        this.queue = trackList || [];
        this.queueIndex = startIndex;
    }

    playNextInQueue() {
        if (this.queue.length === 0 || this.queueIndex + 1 >= this.queue.length) return false;
        this.queueIndex++;
        const nextTrack = this.queue[this.queueIndex];
        if (nextTrack && window.__airnode) {
            window.__airnode.openViewer({
                name: nextTrack.name || nextTrack.title,
                path: nextTrack.path,
                ext: (nextTrack.path || '').split('.').pop()
            });
            return true;
        }
        return false;
    }

    playPrevInQueue() {
        if (this.queue.length === 0 || this.queueIndex - 1 < 0) return false;
        this.queueIndex--;
        const prevTrack = this.queue[this.queueIndex];
        if (prevTrack && window.__airnode) {
            window.__airnode.openViewer({
                name: prevTrack.name || prevTrack.title,
                path: prevTrack.path,
                ext: (prevTrack.path || '').split('.').pop()
            });
            return true;
        }
        return false;
    }

    // Sleep Timer with smooth volume fade-out
    startSleepTimer(minutes) {
        this.clearSleepTimer();
        if (minutes <= 0) return;

        const durationMs = minutes * 60 * 1000;
        this.sleepTimerEndTime = Date.now() + durationMs;

        // Schedule smooth fade out 15s before end
        const fadeStartMs = Math.max(0, durationMs - 15000);
        
        setTimeout(() => {
            this.fadeVolumeAndStop();
        }, fadeStartMs);

        this.notifyListeners();
    }

    clearSleepTimer() {
        if (this.sleepTimerId) {
            clearTimeout(this.sleepTimerId);
            this.sleepTimerId = null;
        }
        this.sleepTimerEndTime = null;
        this.notifyListeners();
    }

    fadeVolumeAndStop() {
        if (!this.activeMedia || !this.isPlaying) return;
        const initialVol = this.volume;
        const fadeInterval = setInterval(() => {
            if (!this.activeMedia || this.activeMedia.volume <= 0.05) {
                clearInterval(fadeInterval);
                this.stopAll();
                if (this.activeMedia) this.activeMedia.volume = initialVol;
                this.clearSleepTimer();
            } else {
                this.activeMedia.volume = Math.max(0, this.activeMedia.volume - 0.08);
            }
        }, 800);
    }

    // Lock-screen MediaSession API integration
    setupMediaSession() {
        if (!('mediaSession' in navigator)) return;

        try {
            navigator.mediaSession.setActionHandler('play', () => this.togglePlayPause());
            navigator.mediaSession.setActionHandler('pause', () => this.togglePlayPause());
            navigator.mediaSession.setActionHandler('previoustrack', () => this.playPrevInQueue());
            navigator.mediaSession.setActionHandler('nexttrack', () => this.playNextInQueue());
            navigator.mediaSession.setActionHandler('seekto', (details) => {
                if (details.seekTime !== undefined) this.seekTo(details.seekTime);
            });
        } catch (e) {}
    }

    updateMediaSession() {
        if (!('mediaSession' in navigator) || !this.currentTrack) return;

        try {
            navigator.mediaSession.metadata = new MediaMetadata({
                title: this.currentTrack.title,
                artist: this.currentTrack.artist,
                album: this.currentTrack.album,
            });
        } catch (e) {}
    }

    subscribe(listener) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    notifyListeners() {
        this.listeners.forEach(fn => fn(this));
    }
}

// Global Singleton Instance
window.AirNodePlayer = new AirNodeMediaManager();
