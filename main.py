import os
import time
import random
from dotenv import load_dotenv
from form_reader import fill_and_submit_google_form
from ai_engine import analyze_form

load_dotenv(override=True)


def load_personas(filepath: str = "personas.txt") -> list[str]:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            if lines:
                return lines
    return [
        "Người tham gia khảo sát phổ thông, trả lời khách quan, tự nhiên và trung thực theo trải nghiệm thực tế."
    ]


def main():
    url = input("Nhap Google Forms URL: ").strip()
    mode = input("Chon che do (1 = Tu nhap 1 luot | 2 = Tu dong dien nhieu luot theo file personas.txt): ").strip()

    try:
        if mode == "2":
            personas = load_personas()
            print(f"Da tai {len(personas)} doi tuong khao sat tu personas.txt.")
            count = int(input("Nhap so luot muon gui len Google Form (vi du 5): ").strip())
            for i in range(count):
                persona = personas[i % len(personas)]
                print(f"\n--- Dang xu ly luot {i + 1}/{count} ---")
                ok = fill_and_submit_google_form(url, analyze_form, persona, headless=False)
                if ok:
                    print(f"[OK] Da gui thanh cong luot {i + 1} len Google Form!")
                if i < count - 1:
                    wait_sec = random.randint(3, 6)
                    print(f"Doi {wait_sec}s truoc khi gui luot tiep theo...")
                    time.sleep(wait_sec)
        else:
            user_context = input("Nhap thong tin/boi canh nguoi tra loi: ").strip()
            print("\nDang mo trinh duyet, dien va gui len Google Form...")
            ok = fill_and_submit_google_form(url, analyze_form, user_context, headless=False)
            if ok:
                print("\n[OK] Da gui cau tra loi thanh cong len Google Form!")

    except Exception as e:
        print("\nERROR:", e)


if __name__ == "__main__":
    main()
