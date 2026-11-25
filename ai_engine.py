import os
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class QuestionSuggestion(BaseModel):
    question: str = Field(description="Nội dung câu hỏi gốc")
    type: str = Field(description="Loại câu hỏi")
    suggested_answers: list[str] = Field(
        description="Danh sách câu trả lời được đề xuất dựa trên thông tin người dùng"
    )
    reason: str = Field(description="Giải thích ngắn gọn lý do chọn đáp án này")
    needs_user_input: bool = Field(
        description="True nếu thiếu thông tin thực tế, ngược lại là False"
    )


class FormAnalysisResult(BaseModel):
    questions: list[QuestionSuggestion]


def _local_fallback_answers(questions: list[dict], user_context: str) -> dict:
    """Phương án dự phòng chạy tại máy khi toàn bộ server Gemini quá tải/chậm."""
    print("[!] Cac server Gemini phan hoi cham, chuyen sang che do dien du phong nhanh...")
    fallback_questions = []
    sample_texts = [
        "Không có ý kiến khác.",
        "Tôi đồng ý với các nội dung trên.",
        "Trải nghiệm ở mức ổn, đáp ứng được nhu cầu cơ bản.",
        "Cần cải thiện thêm để thuận tiện hơn cho người dùng."
    ]
    for q in questions:
        opts = q.get("options", [])
        q_type = q.get("type", "unknown")
        if q_type == "checkboxes" and opts:
            k = min(len(opts), random.randint(1, 2))
            chosen = random.sample(opts, k)
        elif opts:
            chosen = [random.choice(opts)]
        else:
            chosen = [random.choice(sample_texts)]

        fallback_questions.append({
            "question": q["question"],
            "type": q_type,
            "suggested_answers": chosen,
            "reason": "Tự động chọn dự phòng do server AI phản hồi chậm",
            "needs_user_input": False
        })
    return {"questions": fallback_questions}


def _call_gemini_with_timeout(client, model_name: str, prompt: str, timeout_sec: int = 15) -> str:
    """Gọi API với giới hạn thời gian cứng, quá timeout_sec giây tự ngắt ngay."""
    def _task():
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FormAnalysisResult,
                temperature=0.4,
            ),
        )
        return response.text

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_task)
    try:
        return future.result(timeout=timeout_sec)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def analyze_form(questions: list[dict], user_context: str) -> dict:
    """Phân tích danh sách câu hỏi, tự động chuyển model sau tối đa 15s nếu treo."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Chưa cấu hình GEMINI_API_KEY trong file .env")

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

    prompt = f"""
Bạn là trợ lý AI chuyên hỗ trợ điền Google Forms khảo sát thực tế.
Dưới đây là thông tin thực tế của người tham gia khảo sát:
\"\"\"{user_context}\"\"\"

Hãy phân tích danh sách câu hỏi dưới đây và đưa ra câu trả lời hoàn chỉnh để điền trực tiếp vào form:
{json.dumps(questions, ensure_ascii=False, indent=2)}

Quy tắc bắt buộc:
1. Nếu câu hỏi có danh sách `options` (trắc nghiệm, hộp kiểm, dropdown), BẮT BUỘC chọn giá trị khớp chính xác 100% với chuỗi trong `options`.
   - Với `multiple_choice` hoặc `dropdown`: chỉ trả về đúng 1 phần tử trong `suggested_answers`.
   - Với `checkboxes`: có thể chọn từ 1 đến 3 phương án phù hợp nhất trong `options`.
   - Với `multiple_choice_grid`: trả về danh sách các cột tương ứng theo thứ tự từng hàng.
2. Nếu câu hỏi là `short_answer` hoặc `paragraph`: hãy viết câu trả lời tự nhiên, chân thực bằng tiếng Việt đúng văn phong người được mô tả.
3. Không được để `suggested_answers` rỗng.
"""

    models_to_try = [
        "gemini-4-hydrogen",
        "gemini-4-neon",
        "antigravity-preview-latest",
        "gemini-3.8-flash",
    ]
    backoff_delays = [1, 2]

    for attempt, delay in enumerate(backoff_delays, 1):
        for model_name in models_to_try:
            try:
                print(f"[->] Vong {attempt} - Dang goi {model_name} (toi da 15s)...")
                raw_text = _call_gemini_with_timeout(client, model_name, prompt, timeout_sec=15)
                return json.loads(raw_text)
            except FuturesTimeoutError:
                print(f"[!] {model_name} qua 15s khong phan hoi, chuyen ngay sang model khac...")
                continue
            except Exception as e:
                err_str = str(e)
                if any(code in err_str for code in ["503", "UNAVAILABLE", "429", "500", "404", "400"]):
                    print(f"[!] {model_name} ban/loi tam thoi, doi {delay}s roi chuyen model...")
                    time.sleep(delay)
                    continue
                raise e

    return _local_fallback_answers(questions, user_context)
