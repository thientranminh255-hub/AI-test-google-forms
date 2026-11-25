import re
import unicodedata
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFC", text).strip().lower()


def _validate_url(url: str):
    parsed = urlparse(url)
    allowed_hosts = {"docs.google.com", "forms.gle"}
    if parsed.hostname not in allowed_hosts:
        raise ValueError("URL không phải Google Forms.")


def _extract_questions_on_current_page(page) -> list[dict]:
    items = page.locator('div[role="listitem"]')
    results = []

    for i in range(items.count()):
        item = items.nth(i)
        title = item.locator('.M7eMe').first
        if title.count() == 0:
            continue

        question_text = title.inner_text().strip()
        if not question_text:
            continue

        question_text = re.sub(
            r"^Câu\s+\d+\s*:\s*", "", question_text, count=1, flags=re.IGNORECASE
        )

        # Kiểm tra xem có phải dạng Lưới (Grid - nhiều nhóm radiogroup/checkbox theo hàng)
        radio_groups = item.locator('[role="radiogroup"]')
        if radio_groups.count() > 1:
            row_names = []
            col_names = []
            for r_idx in range(radio_groups.count()):
                rg = radio_groups.nth(r_idx)
                r_label = rg.get_attribute("aria-label") or f"Hàng {r_idx + 1}"
                row_names.append(r_label.strip())
                if r_idx == 0:
                    opts = rg.locator('[role="radio"]')
                    for o_idx in range(opts.count()):
                        opt_lbl = opts.nth(o_idx).get_attribute("aria-label") or ""
                        if opt_lbl:
                            col_names.append(opt_lbl.strip())
            results.append({
                "index": i,
                "question": f"{question_text} (Các hàng: {', '.join(row_names)})",
                "type": "multiple_choice_grid",
                "options": col_names
            })
            continue

        options = item.locator('[role="radio"], [role="checkbox"]')
        option_texts = []
        for j in range(options.count()):
            option = options.nth(j)
            option_text = option.get_attribute("aria-label") or option.inner_text()
            if option_text and option_text.strip():
                option_texts.append(option_text.strip())

        if item.locator('[role="radio"]').count():
            # Kiểm tra xem có phải Thang đo tuyến tính (Linear Scale 1 -> 5) không
            radios = item.locator('[role="radio"]')
            first_lbl = (radios.first.get_attribute("aria-label") or "").strip()
            last_lbl = (radios.last.get_attribute("aria-label") or "").strip()
            if first_lbl.isdigit() and last_lbl.isdigit():
                question_type = "linear_scale"
                # Lấy nhãn mô tả 2 đầu thang đo (ví dụ: Không hề khó khăn <-> Rất khó khăn)
                scale_texts = [t.strip() for t in item.locator('.V4d7Ke, .Zki2Ve, .OIC90c').all_inner_texts() if t.strip() and not t.strip().isdigit()]
                low_desc = scale_texts[0] if len(scale_texts) >= 1 else "Mức thấp nhất / Rất dễ"
                high_desc = scale_texts[-1] if len(scale_texts) >= 2 else "Mức cao nhất / Rất khó"
                option_texts = [
                    f"{opt} ({low_desc})" if idx == 0 else (f"{opt} ({high_desc})" if idx == len(option_texts) - 1 else opt)
                    for idx, opt in enumerate(option_texts)
                ]
            else:
                question_type = "multiple_choice"
        elif item.locator('[role="checkbox"]').count():
            question_type = "checkboxes"
        elif item.locator('[role="listbox"]').count():
            question_type = "dropdown"
            dd_options = item.locator('[role="option"]')
            for j in range(dd_options.count()):
                txt = dd_options.nth(j).inner_text().strip()
                if txt and txt != "Chọn":
                    option_texts.append(txt)
        elif item.locator("textarea").count():
            question_type = "paragraph"
        elif item.locator('input[type="text"], input[type="email"], input[type="number"]').count():
            question_type = "short_answer"
        else:
            question_type = "unknown"

        results.append({
            "index": i,
            "question": question_text,
            "type": question_type,
            "options": option_texts
        })

    return results


def _find_action_button(page, keywords: list[str]):
    buttons = page.locator('div[role="button"], button')
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        if not btn.is_visible():
            continue
        txt = _normalize_text(btn.inner_text())
        aria = _normalize_text(btn.get_attribute("aria-label") or "")
        for kw in keywords:
            if txt == kw or kw in txt.split() or aria == kw:
                return btn
    return None


def _fill_single_item(page, item, q_type: str, chosen: list[str]):
    """Điền đáp án cho 1 khối câu hỏi cụ thể và đảm bảo không bỏ sót."""
    if q_type == "multiple_choice_grid":
        radio_groups = item.locator('[role="radiogroup"]')
        for r_idx in range(radio_groups.count()):
            rg = radio_groups.nth(r_idx)
            radios = rg.locator('[role="radio"]')
            if radios.count() == 0:
                continue
            target = _normalize_text(chosen[r_idx] if r_idx < len(chosen) else chosen[0])
            clicked = False
            for j in range(radios.count()):
                r = radios.nth(j)
                lbl = _normalize_text(r.get_attribute("aria-label") or "")
                if lbl == target or (target and target in lbl):
                    r.scroll_into_view_if_needed()
                    r.click()
                    clicked = True
                    break
            if not clicked:
                radios.nth(min(1, radios.count() - 1)).click()

    elif q_type == "multiple_choice" or item.locator('[role="radio"]').count():
        radios = item.locator('[role="radio"]')
        target = _normalize_text(chosen[0]) if chosen else ""
        clicked = False
        for j in range(radios.count()):
            r = radios.nth(j)
            label = _normalize_text(r.get_attribute("aria-label") or r.inner_text())
            if label == target or (target and target in label):
                r.scroll_into_view_if_needed()
                r.click()
                clicked = True
                break
        if not clicked and radios.count() > 0:
            radios.first.scroll_into_view_if_needed()
            radios.first.click()

    elif q_type == "checkboxes" or item.locator('[role="checkbox"]').count():
        checkboxes = item.locator('[role="checkbox"]')
        any_clicked = False
        for target in chosen:
            target_clean = _normalize_text(target)
            for j in range(checkboxes.count()):
                cb = checkboxes.nth(j)
                label = _normalize_text(cb.get_attribute("aria-label") or cb.inner_text())
                if label == target_clean or (target_clean and target_clean in label):
                    if cb.get_attribute("aria-checked") != "true":
                        cb.scroll_into_view_if_needed()
                        cb.click()
                    any_clicked = True
                    break
        if not any_clicked and checkboxes.count() > 0:
            checkboxes.first.scroll_into_view_if_needed()
            checkboxes.first.click()

    elif q_type == "dropdown" or item.locator('[role="listbox"]').count():
        listbox = item.locator('[role="listbox"]').first
        listbox.scroll_into_view_if_needed()
        listbox.click()
        page.wait_for_timeout(500)
        target = chosen[0].strip() if chosen else ""
        opts = page.locator('div[role="option"]')
        clicked = False
        for j in range(opts.count()):
            opt = opts.nth(j)
            txt = opt.inner_text().strip()
            if txt and txt != "Chọn" and (_normalize_text(txt) == _normalize_text(target) or _normalize_text(target) in _normalize_text(txt)):
                opt.click()
                clicked = True
                break
        if not clicked and opts.count() > 1:
            opts.nth(1).click()
        page.wait_for_timeout(400)

    elif q_type == "paragraph" or item.locator("textarea").count():
        ta = item.locator("textarea").first
        ta.scroll_into_view_if_needed()
        ta.fill(chosen[0] if chosen else "Tôi đồng ý với các ý kiến trên.")
        ta.press("Tab")

    elif q_type == "short_answer" or item.locator('input[type="text"], input[type="email"], input[type="number"]').count():
        inp = item.locator('input[type="text"], input[type="email"], input[type="number"]').first
        inp.scroll_into_view_if_needed()
        val = chosen[0] if chosen else "Không có"
        if inp.get_attribute("type") == "email" and "@" not in val:
            val = "nguoithan.khaosat@gmail.com"
        inp.fill(val)
        inp.press("Tab")


def read_google_form(url: str) -> list[dict]:
    _validate_url(url)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="./browser_profile",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            return _extract_questions_on_current_page(page)
        finally:
            context.close()


def fill_and_submit_google_form(url: str, analyze_callback, user_context: str, headless: bool = False) -> bool:
    """Mở form (lưu phiên đăng nhập Google), điền chính xác 100% câu hỏi và bấm Gửi."""
    _validate_url(url)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="./browser_profile",
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Tự động phát hiện nếu Google Form yêu cầu đăng nhập
            if "accounts.google.com" in page.url or page.locator('text="Đăng nhập để tiếp tục"').count() > 0 or page.locator('text="Sign in to continue"').count() > 0:
                print("\n[!] Form nay yeu cau dang nhap tai khoan Google.")
                print("    -> Hay dang nhap Gmail truc tiep tren cua so trinh duyet vua mo.")
                input("    -> Sau khi dang nhap xong va thay trang cau hoi hien ra, bam ENTER tai day de tiep tuc...")
                page.wait_for_timeout(1500)

            while True:
                page_questions = _extract_questions_on_current_page(page)
                if page_questions:
                    ai_result = analyze_callback(page_questions, user_context)
                    suggestions = ai_result.get("questions", [])

                    items = page.locator('div[role="listitem"]')

                    for idx, q_meta in enumerate(page_questions):
                        item = items.nth(q_meta["index"])
                        chosen = (
                            suggestions[idx]["suggested_answers"]
                            if idx < len(suggestions) and suggestions[idx].get("suggested_answers")
                            else ["Có"]
                        )
                        _fill_single_item(page, item, q_meta["type"], chosen)
                        page.wait_for_timeout(150)

                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)

                submit_btn = _find_action_button(page, ["gửi", "submit", "hoàn tất", "send"])
                next_btn = _find_action_button(page, ["tiếp", "next", "tiếp theo"])

                if submit_btn:
                    submit_btn.scroll_into_view_if_needed()
                    submit_btn.click()
                    page.wait_for_timeout(2500)

                    # Kiểm tra nếu Google Form báo lỗi "Đây là một câu hỏi bắt buộc"
                    if page.locator('text="Đây là một câu hỏi bắt buộc"').count() > 0 or page.locator('text="This is a required question"').count() > 0:
                        print("[!] Phat hien cau hoi bat buoc bi sot, dang tu dong dien bo sung...")
                        items = page.locator('div[role="listitem"]')
                        for k in range(items.count()):
                            it = items.nth(k)
                            if it.locator('text="Đây là một câu hỏi bắt buộc"').count() > 0 or it.locator('text="This is a required question"').count() > 0:
                                _fill_single_item(page, it, "unknown", ["Không có ý kiến khác"])
                        page.wait_for_timeout(500)
                        submit_btn.click()
                        page.wait_for_timeout(2500)

                    return True

                elif next_btn:
                    next_btn.scroll_into_view_if_needed()
                    next_btn.click()
                    page.wait_for_timeout(1500)
                else:
                    visible_btns = [
                        b.inner_text().strip()
                        for b in page.locator('div[role="button"], button').all()
                        if b.is_visible() and b.inner_text().strip()
                    ]
                    raise RuntimeError(f"Không tìm thấy nút Gửi/Tiếp. Các nút trên trang: {visible_btns}")

        finally:
            context.close()
