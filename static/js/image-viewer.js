/**
 * AirNode Image Viewer
 * Alpine.js component — register via Alpine.data('imageViewer', imageViewerComponent)
 *
 * Handles:
 *  - Double-tap to toggle zoom (1x <-> 2.5x)
 *  - Pinch-to-zoom (two finger)
 *  - Drag to pan when zoomed
 *  - Swipe left/right to navigate between images in current directory
 *  - Auto-hide header when zoomed
 *  - Loading/error states
 */

function imageViewerComponent() {
    return {
        // ── State ────────────────────────────────────────────────
        scale: 1,
        translateX: 0,
        translateY: 0,
        loading: true,
        error: false,

        // Gesture tracking
        _lastTap: 0,
        _isDragging: false,
        _dragStartX: 0,
        _dragStartY: 0,
        _panOriginX: 0,
        _panOriginY: 0,

        // Pinch tracking
        _pinchStartDist: 0,
        _pinchStartScale: 1,
        _activePointers: {},

        // Swipe tracking
        _swipeStartX: 0,
        _swipeStartY: 0,
        _isSwiping: false,

        // ── Helpers ──────────────────────────────────────────────
        get transform() {
            return `scale(${this.scale}) translate(${this.translateX}px, ${this.translateY}px)`;
        },

        get isZoomed() {
            return this.scale > 1.05;
        },

        get headerHidden() {
            return this.isZoomed;
        },

        resetTransform() {
            this.scale = 1;
            this.translateX = 0;
            this.translateY = 0;
        },

        clampPan() {
            // Limit pan so image doesn't wander completely off screen
            const maxPan = (this.scale - 1) * 50;
            this.translateX = Math.max(-maxPan, Math.min(maxPan, this.translateX));
            this.translateY = Math.max(-maxPan, Math.min(maxPan, this.translateY));
        },

        // ── Image navigation ─────────────────────────────────────
        getImageList() {
            const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'heic'];
            return Array.from(document.querySelectorAll('.file-row'))
                .filter(row => imageExts.includes((row.dataset.ext || '').toLowerCase()))
                .map(row => {
                    // Extract path and name from the row's click handler data
                    const btn = row.querySelector('.row-btn');
                    if (!btn) return null;
                    // Read from the onclick which sets file.path / file.name
                    // Fall back to data-name for the label
                    return {
                        name: row.dataset.name,
                        // The path is embedded in the Alpine click handler —
                        // we store it as a data attribute in file_list.html
                        path: row.dataset.path,
                    };
                })
                .filter(Boolean);
        },

        navigate(direction) {
            const images = this.getImageList();
            if (images.length < 2) return;

            if (!window.__airnode || !window.__airnode.viewer) return;
            const currentPath = window.__airnode.viewer.path;

            const idx = images.findIndex(img => img.path === currentPath);
            if (idx === -1) return;

            const nextIdx = (idx + direction + images.length) % images.length;
            const next = images[nextIdx];

            window.__airnode.viewer = {
                name: next.name,
                path: next.path,
                kind: 'img',
            };

            this.resetTransform();
            this.loading = true;
            this.error = false;
        },

        // ── Double-tap zoom ──────────────────────────────────────
        onTap(event) {
            // Don't handle taps on nav buttons
            if (event.target.closest('.img-nav-btn')) return;

            const now = Date.now();
            const DOUBLE_TAP_MS = 280;

            if (now - this._lastTap < DOUBLE_TAP_MS) {
                // Double tap — toggle zoom
                if (this.isZoomed) {
                    this.resetTransform();
                } else {
                    this.scale = 2.5;
                    // Zoom toward tap point
                    const rect = event.currentTarget.getBoundingClientRect();
                    const cx = rect.width / 2;
                    const cy = rect.height / 2;
                    this.translateX = (cx - event.clientX + rect.left) / this.scale * 0.4;
                    this.translateY = (cy - event.clientY + rect.top) / this.scale * 0.4;
                }
                this._lastTap = 0;
            } else {
                this._lastTap = now;
            }
        },

        // ── Pointer events (drag + pinch + swipe) ────────────────
        onPointerDown(event) {
            // Don't hijack pointer capture for nav button taps —
            // setPointerCapture() on the stage steals all subsequent
            // events for this pointer, which silently breaks the
            // button's own click event.
            if (event.target.closest('.img-nav-btn')) return;

            this._activePointers[event.pointerId] = { x: event.clientX, y: event.clientY };
            const pointerCount = Object.keys(this._activePointers).length;

            if (pointerCount === 1) {
                this._swipeStartX = event.clientX;
                this._swipeStartY = event.clientY;
                this._isSwiping = !this.isZoomed; // only swipe when not zoomed

                this._dragStartX = event.clientX;
                this._dragStartY = event.clientY;
                this._panOriginX = this.translateX;
                this._panOriginY = this.translateY;
                this._isDragging = false;
            }

            if (pointerCount === 2) {
                this._isSwiping = false;
                const pts = Object.values(this._activePointers);
                this._pinchStartDist = Math.hypot(
                    pts[1].x - pts[0].x,
                    pts[1].y - pts[0].y
                );
                this._pinchStartScale = this.scale;
            }

            event.currentTarget.setPointerCapture(event.pointerId);
        },

        onPointerMove(event) {
            if (event.target.closest('.img-nav-btn')) return;
            if (!this._activePointers[event.pointerId]) return;
            this._activePointers[event.pointerId] = { x: event.clientX, y: event.clientY };

            const pointerCount = Object.keys(this._activePointers).length;

            if (pointerCount === 2) {
                // Pinch zoom
                const pts = Object.values(this._activePointers);
                const dist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
                const newScale = Math.max(1, Math.min(5, this._pinchStartScale * (dist / this._pinchStartDist)));
                this.scale = newScale;
                if (newScale <= 1) { this.translateX = 0; this.translateY = 0; }
                return;
            }

            if (pointerCount === 1 && this.isZoomed) {
                // Pan when zoomed
                this._isDragging = true;
                this._isSwiping = false;
                const dx = (event.clientX - this._dragStartX) / this.scale;
                const dy = (event.clientY - this._dragStartY) / this.scale;
                this.translateX = this._panOriginX + dx;
                this.translateY = this._panOriginY + dy;
                this.clampPan();
            }
        },

        onPointerUp(event) {
            const wasSwiping = this._isSwiping;
            const swipeDx = event.clientX - this._swipeStartX;
            const swipeDy = Math.abs(event.clientY - this._swipeStartY);

            delete this._activePointers[event.pointerId];
            this._isSwiping = false;

            // Swipe threshold: horizontal > 60px and mostly horizontal
            if (wasSwiping && Math.abs(swipeDx) > 60 && swipeDy < 80) {
                this.navigate(swipeDx < 0 ? 1 : -1);
            }
        },

        onPointerCancel(event) {
            delete this._activePointers[event.pointerId];
        },

        // ── Keyboard navigation ──────────────────────────────────
        onKeydown(event) {
            if (!window.__airnode?.viewer) return;
            if (event.key === 'ArrowRight') this.navigate(1);
            if (event.key === 'ArrowLeft')  this.navigate(-1);
            if (event.key === 'Escape')     window.__airnode.closeViewer();
            if (event.key === '0')          this.resetTransform();
        },

        // ── Lifecycle ────────────────────────────────────────────
        init() {
            this.loading = true;
            this.error = false;
            this.resetTransform();
            window.addEventListener('keydown', e => this.onKeydown(e));
        },
    };
}