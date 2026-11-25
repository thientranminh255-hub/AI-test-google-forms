
from form_reader import read_google_form

url = input("Nhap Google Forms URL: ")

try:
    questions = read_google_form(url)

    for i, q in enumerate(questions, 1):
        print(f"\nCau {i}: {q['question']}")
        print(f"Loai: {q['type']}")
        print(f"Lua chon: {q['options']}")

    print(f"\nTong so cau hoi: {len(questions)}")

except Exception as e:
    print("Loi:", e)
