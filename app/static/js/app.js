/* 全站交互：收藏、删除确认、图片预览、字数统计、画廊切换、Toast 提示 */
(function () {
    "use strict";

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

    /** 右下角轻提示 */
    window.showToast = function (message, type = "info") {
        const stack = document.getElementById("toastStack");
        if (!stack) return;
        const item = document.createElement("div");
        item.className = "toast-item " + type;
        item.textContent = message;
        stack.appendChild(item);
        setTimeout(() => item.remove(), 3200);
    };

    function goLogin() {
        const next = encodeURIComponent(location.pathname + location.search);
        location.href = "/auth/login?next=" + next;
    }

    /* ---------------- 收藏（Ajax，失败有提示） ---------------- */
    document.addEventListener("click", async function (event) {
        const button = event.target.closest("[data-favorite-url]");
        if (!button) return;
        event.preventDefault();

        const url = button.dataset.favoriteUrl;
        button.disabled = true;
        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRF-Token": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            if (response.status === 401) {
                showToast("请先登录再收藏", "error");
                setTimeout(goLogin, 800);
                return;
            }
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.msg || "操作失败");
            }

            button.classList.toggle("favorited", data.favorited);
            const label = button.querySelector("[data-fav-label]");
            if (label) label.textContent = data.favorited ? "已收藏" : "收藏";
            const icon = button.querySelector("[data-fav-icon]");
            if (icon) icon.textContent = data.favorited ? "♥" : "♡";
            const count = document.querySelector("[data-fav-count]");
            if (count) count.textContent = data.count;
            showToast(data.msg, "success");
        } catch (error) {
            showToast(error.message || "网络异常，请稍后重试", "error");
        } finally {
            button.disabled = false;
        }
    });

    /* ---------------- 删除 / 下架等危险操作二次确认 ---------------- */
    document.addEventListener("submit", function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const message = form.dataset.confirm;
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    });

    /* ---------------- 商品图片：选择后本地预览 ---------------- */
    document.querySelectorAll("[data-upload-slot]").forEach(function (slot) {
        const input = slot.querySelector('input[type="file"]');
        if (!input) return;
        input.addEventListener("change", function () {
            const file = input.files && input.files[0];
            const placeholder = slot.querySelector(".slot-placeholder");
            const preview = slot.querySelector(".slot-preview");
            if (!file || !preview) return;

            if (file.size > 2 * 1024 * 1024) {
                showToast("图片不能超过 2MB，请压缩后再上传", "error");
                input.value = "";
                return;
            }
            if (!/\.(jpe?g|png)$/i.test(file.name)) {
                showToast("仅支持 jpg / png 格式", "error");
                input.value = "";
                return;
            }
            preview.src = URL.createObjectURL(file);
            preview.hidden = false;
            if (placeholder) placeholder.hidden = true;
        });
    });

    /* ---------------- 文本域字数统计 ---------------- */
    document.querySelectorAll("[data-counter]").forEach(function (field) {
        const target = document.querySelector(field.dataset.counter);
        if (!target) return;
        const update = () => (target.textContent = field.value.length);
        field.addEventListener("input", update);
        update();
    });

    /* ---------------- 详情页图片切换 ---------------- */
    const mainImage = document.getElementById("galleryMain");
    document.querySelectorAll("[data-gallery-thumb]").forEach(function (thumb) {
        thumb.addEventListener("click", function () {
            if (!mainImage) return;
            mainImage.src = thumb.dataset.galleryThumb;
            document.querySelectorAll("[data-gallery-thumb]").forEach((item) =>
                item.classList.remove("active")
            );
            thumb.classList.add("active");
        });
    });

    /* ---------------- 编辑页：取消保留某张旧图 ---------------- */
    document.querySelectorAll("[data-keep-toggle]").forEach(function (checkbox) {
        checkbox.addEventListener("change", function () {
            const wrapper = checkbox.closest(".existing-image");
            if (wrapper) wrapper.style.opacity = checkbox.checked ? "1" : ".35";
        });
    });

    /* ---------------- 提示条自动消失 ---------------- */
    document.querySelectorAll(".flash-wrap .alert").forEach(function (alert) {
        setTimeout(function () {
            if (window.bootstrap && bootstrap.Alert) {
                bootstrap.Alert.getOrCreateInstance(alert).close();
            }
        }, 4500);
    });
})();
