
from dotenv import load_dotenv

from form_reader import read_google_form
from ai_engine import analyze_form


# Đọc biến môi trường
load_dotenv()


def main():

    url = input("Nhap Google Forms URL: ")

    user_context = input(
        "Nhap thong tin thuc te: "
    )

    try:

        # Bước 1: Đọc biểu mẫu
        print("\nDang doc Google Forms...")

        questions = read_google_form(url)

        print(
            f"Da doc duoc {len(questions)} cau hoi."
        )

        # Bước 2: Phân tích bằng AI
        print("\nAI dang phan tich...")

        result = analyze_form(
            questions,
            user_context
        )

        # Bước 3: Hiển thị kết quả
        print("\n===== AI SUGGESTIONS =====\n")

        for i, q in enumerate(
            result["questions"], 1
        ):

            print(f"Cau {i}: {q['question']}")

            print(f"Loai: {q['type']}")

            print(
                "De xuat:",
                q["suggested_answers"]
            )

            print(
                "Ly do:",
                q["reason"]
            )

            print(
                "Can bo sung:",
                q["needs_user_input"]
            )

            print("-" * 60)

    except Exception as e:

        print("\nERROR:", e)


if __name__ == "__main__":
    main()
