from datetime import date
import time

import streamlit as st

from api.diary import (
    approve_version,
    delete_version,
    create_session,
    confirm_transcript,
    get_job,
    list_versions,
    request_generation,
    review_information,
    send_message,
    start_new_version_chat,
    upload_files,
)


st.title("📔 일기 채팅")
st.caption("HCX-005와 대화한 뒤 HCX-007이 오늘의 일기를 정리합니다.")


def start_new_diary() -> None:
    session = create_session("streamlit-test-user", date.today())
    stored_versions = list_versions(session["session_id"])["versions"]
    st.session_state.diary_session_id = session["session_id"]
    st.session_state.diary_messages = []
    st.session_state.diary_ready = False
    st.session_state.diary_stage = "drafted" if stored_versions else "collecting"
    st.session_state.diary_review_summary = None
    # 저장된 후보는 페이지 진입 시 바로 노출하지 않고 후보 팝업에서만 보여준다.
    st.session_state.diary_result = None
    st.session_state.diary_script_result = None
    st.session_state.diary_versions = stored_versions
    st.session_state.diary_show_versions = False
    st.session_state.diary_pending_audio = None
    st.session_state.diary_audio_editing = False


if "diary_session_id" not in st.session_state:
    try:
        start_new_diary()
    except RuntimeError as exc:
        st.error(str(exc))
        st.code(
            ".venv/bin/python -m uvicorn backend.main:app "
            "--host 127.0.0.1 --port 8000 --reload",
            language="bash",
        )
        if st.button("백엔드 연결 다시 시도", type="primary"):
            st.rerun()
        st.stop()

# Keep hot-reloaded sessions compatible when new UI state keys are introduced.
st.session_state.setdefault("diary_stage", "collecting")
st.session_state.setdefault("diary_review_summary", None)
st.session_state.setdefault("diary_pending_audio", None)
st.session_state.setdefault("diary_audio_editing", False)
st.session_state.setdefault("diary_script_result", None)
st.session_state.setdefault("diary_versions", [])
st.session_state.setdefault("diary_show_versions", False)


def wait_for_generation(job: dict) -> dict:
    for _ in range(60):
        job_status = get_job(job["job_id"])
        if job_status["status"] == "completed":
            return job_status["result"]
        if job_status["status"] == "failed":
            raise RuntimeError(job_status.get("error_code") or "generation failed")
        time.sleep(0.5)
    raise TimeoutError("일기 생성 시간이 초과됐습니다.")


def close_version_picker() -> None:
    st.session_state.diary_show_versions = False


@st.dialog(
    "오늘의 일기 후보",
    width="large",
    on_dismiss=close_version_picker,
)
def show_version_picker() -> None:
    version_data = list_versions(st.session_state.diary_session_id)
    versions = version_data["versions"]
    st.session_state.diary_versions = versions
    if not versions:
        st.info("아직 작성된 일기가 없어요. 오늘의 일기를 작성해 주세요!")
        return
    st.caption(
        f"최대 {version_data['max_versions']}개까지 만들 수 있어요. "
        "마음에 드는 하나를 오늘의 일기로 확정해 주세요."
    )
    for index, version in enumerate(versions, start=1):
        with st.container(border=True):
            label = f"후보 {index} · {version['title']}"
            if version["approved"]:
                label += "  ✅ 확정됨"
            title_col, delete_col = st.columns([8, 1])
            title_col.markdown(f"### {label}")
            if delete_col.button(
                "✕",
                key=f"delete-{version['version_id']}",
                help="이 일기 후보 삭제",
            ):
                delete_version(
                    st.session_state.diary_session_id,
                    version["version_id"],
                )
                if (
                    st.session_state.diary_result
                    and st.session_state.diary_result.get("version_id")
                    == version["version_id"]
                ):
                    st.session_state.diary_result = None
                    st.session_state.diary_script_result = None
                st.rerun()
            for paragraph in version["paragraphs"]:
                st.write(paragraph)
            if version.get("emotion_tags"):
                st.caption("감정 태그: " + ", ".join(version["emotion_tags"]))
            if st.button(
                "확정된 일기" if version["approved"] else "이 일기를 오늘의 일기로 확정",
                key=f"approve-{version['version_id']}",
                type="primary" if not version["approved"] else "secondary",
                disabled=version["approved"],
                use_container_width=True,
            ):
                selected = approve_version(
                    st.session_state.diary_session_id,
                    version["version_id"],
                )
                st.session_state.diary_result = selected
                with st.spinner("확정한 일기의 나레이션 대본을 만들고 있어요..."):
                    st.session_state.diary_script_result = wait_for_generation(
                        {"job_id": selected["media_job_id"]}
                    )
                st.session_state.diary_show_versions = False
                st.rerun()

    if version_data["can_create_new_version"]:
        st.caption("다른 후보는 팝업을 닫고 ‘새 일기 쓰기’에서 새 채팅으로 작성해 주세요.")
    else:
        st.info(
            "일기는 최대 3개까지 생성할 수 있어요. "
            "일기 후보 중 하나를 삭제하고 다시 써보세요."
        )

action_col, versions_col = st.columns(2)
if action_col.button("＋ 새 일기 쓰기", use_container_width=True):
    try:
        response = start_new_version_chat(st.session_state.diary_session_id)
        st.session_state.diary_messages = []
        st.session_state.diary_ready = False
        st.session_state.diary_stage = response["stage"]
        st.session_state.diary_review_summary = None
        st.session_state.diary_result = None
        st.session_state.diary_script_result = None
        st.session_state.diary_pending_audio = None
        st.session_state.diary_audio_editing = False
        st.session_state.diary_show_versions = False
        st.rerun()
    except RuntimeError as exc:
        st.error(str(exc))

if versions_col.button("📚 오늘의 일기 후보", use_container_width=True):
    st.session_state.diary_show_versions = True

def render_image_analysis(message: dict) -> None:
    observations = message.get("image_observations") or []
    clarity_notes = message.get("image_clarity") or []
    evidence_ids = set(message.get("image_evidence_ids") or [])
    if not observations and not clarity_notes:
        return
    with st.expander("📷 사진 분석 결과", expanded=True):
        for observation in observations:
            st.write(observation.get("description") or "사진 내용을 확인하지 못했어요.")
            facts = observation.get("observed_facts") or []
            if facts:
                st.caption("확인한 시각 정보: " + ", ".join(facts))
            if observation.get("related_event"):
                st.caption("연결된 이야기: " + observation["related_event"])
            if observation.get("input_id") in evidence_ids:
                st.caption("✓ 이 사진은 사건의 근거로 사용됐어요.")
        for note in clarity_notes:
            if note.get("unclear"):
                st.warning("사진 판별이 어려웠어요: " + (note.get("reason") or "내용이 불분명해요."))


def apply_chat_response(response: dict) -> None:
    turn = response["turn"]
    turn_response = turn.get("response", {})
    assistant_text = turn_response.get("reaction") or "이야기를 기록했어요."
    if turn_response.get("question"):
        assistant_text += f"\n\n{turn_response['question']}"
    image_evidence_ids = {
        evidence["input_id"]
        for event in turn.get("events", [])
        for evidence in event.get("evidence", [])
        if evidence.get("input_id")
    }
    st.session_state.diary_messages.append({
        "role": "assistant",
        "content": assistant_text,
        "image_observations": turn.get("image_observations", []),
        "image_clarity": turn.get("image_clarity", []),
        "image_evidence_ids": sorted(image_evidence_ids),
    })
    st.session_state.diary_ready = response["stage"] == "ready_to_generate"
    st.session_state.diary_stage = response["stage"]
    st.session_state.diary_review_summary = response.get("review_summary")


def send_prepared_turn(prompt: str, input_ids: list[str]) -> None:
    response = send_message(st.session_state.diary_session_id, prompt, input_ids)
    apply_chat_response(response)


for message in st.session_state.diary_messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        render_image_analysis(message)

stage = st.session_state.diary_stage
accepting_text = stage in {
    "collecting", "needs_clarification", "adding_more_content", "awaiting_correction"
}
pending_audio = st.session_state.diary_pending_audio

if pending_audio:
    st.info("음성 메모를 이렇게 인식했어요. 내용이 맞는지 확인해 주세요.")
    edited_transcripts = {}
    for item in pending_audio["audio_items"]:
        st.caption(f"🎙️ {item['input_id']}")
        if st.session_state.diary_audio_editing:
            edited_transcripts[item["input_id"]] = st.text_area(
                "인식된 내용 수정",
                value=item["transcript"],
                key=f"audio-transcript-{item['input_id']}",
            )
        else:
            st.write(item["transcript"])

    if st.session_state.diary_audio_editing:
        save_col, cancel_col = st.columns(2)
        if save_col.button("수정 내용 확인", type="primary", use_container_width=True):
            try:
                for item in pending_audio["audio_items"]:
                    transcript = edited_transcripts[item["input_id"]]
                    confirm_transcript(
                        st.session_state.diary_session_id,
                        item["input_id"],
                        transcript,
                    )
                with st.spinner("확정한 음성 내용을 기록하고 있어요..."):
                    send_prepared_turn(pending_audio["prompt"], pending_audio["input_ids"])
                st.session_state.diary_pending_audio = None
                st.session_state.diary_audio_editing = False
                st.rerun()
            except Exception as exc:
                st.error(f"음성 메모 확인 실패: {exc}")
        if cancel_col.button("취소", use_container_width=True):
            st.session_state.diary_audio_editing = False
            st.rerun()
    else:
        yes_col, edit_col = st.columns(2)
        if yes_col.button("맞아요", type="primary", use_container_width=True):
            try:
                for item in pending_audio["audio_items"]:
                    confirm_transcript(
                        st.session_state.diary_session_id,
                        item["input_id"],
                        item["transcript"],
                    )
                with st.spinner("확정한 음성 내용을 기록하고 있어요..."):
                    send_prepared_turn(pending_audio["prompt"], pending_audio["input_ids"])
                st.session_state.diary_pending_audio = None
                st.rerun()
            except Exception as exc:
                st.error(f"음성 메모 확인 실패: {exc}")
        if edit_col.button("수정할게요", use_container_width=True):
            st.session_state.diary_audio_editing = True
            st.rerun()

if stage == "awaiting_summary_confirmation":
    st.info(
        "오늘을 요약해봤어요. 제가 잘 이해한 게 맞나요?\n\n"
        + (st.session_state.diary_review_summary or "오늘의 이야기를 정리했어요.")
    )
    yes_col, no_col = st.columns(2)
    if yes_col.button("네, 맞아요", type="primary", use_container_width=True):
        response = review_information(st.session_state.diary_session_id, "summary_yes")
        st.session_state.diary_stage = response["stage"]
        st.rerun()
    if no_col.button("아니요", use_container_width=True):
        response = review_information(st.session_state.diary_session_id, "summary_no")
        st.session_state.diary_stage = response["stage"]
        st.rerun()

if stage == "awaiting_more_content":
    st.info("더 기록하고 싶은 내용이 있나요?")
    yes_col, no_col = st.columns(2)
    if yes_col.button("네, 더 입력할게요", type="primary", use_container_width=True):
        response = review_information(st.session_state.diary_session_id, "more_yes")
        st.session_state.diary_stage = response["stage"]
        st.rerun()
    if no_col.button("아니요, 일기를 만들게요", use_container_width=True):
        response = review_information(st.session_state.diary_session_id, "more_no")
        st.session_state.diary_stage = response["stage"]
        st.session_state.diary_ready = response["stage"] == "ready_to_generate"
        st.rerun()

if stage == "awaiting_correction":
    st.warning("제가 잘못 알고 있는 내용을 알려주세요!")
elif stage == "adding_more_content":
    st.info("추가로 기록하고 싶은 내용을 입력해 주세요.")

if stage == "needs_clarification" and not pending_audio:
    if st.button("이 질문은 건너뛸게요"):
        try:
            response = review_information(
                st.session_state.diary_session_id,
                "skip_current",
            )
            if response.get("turn"):
                apply_chat_response(response)
            else:
                st.session_state.diary_stage = response["stage"]
                st.session_state.diary_review_summary = response.get("review_summary")
            st.rerun()
        except Exception as exc:
            st.error(f"질문 건너뛰기 실패: {exc}")

if accepting_text and not pending_audio:
    submission = st.chat_input(
        "오늘 있었던 일을 이야기하거나 사진·음성을 첨부해 주세요",
        accept_file="multiple",
        file_type=["jpg", "jpeg", "png", "webp", "wav", "mp3", "m4a", "aac"],
    )
    if submission:
        prompt = submission.text
        files = list(submission.files)
        visible_message = prompt or f"첨부 파일 {len(files)}개를 보냈어요."
        st.session_state.diary_messages.append({"role": "user", "content": visible_message})
        with st.chat_message("user"):
            st.write(visible_message)
            for uploaded in files:
                st.caption(f"📎 {uploaded.name}")
        try:
            with st.spinner("Mediary가 기록을 정리하고 있어요..."):
                input_ids = []
                if files:
                    preprocessed = upload_files(st.session_state.diary_session_id, files)
                    failed = [item for item in preprocessed["items"] if item["status"] == "failed"]
                    if failed:
                        raise RuntimeError(failed[0].get("error_reason") or "첨부 전처리 실패")
                    input_ids = [item["input_id"] for item in preprocessed["items"]]
                    audio_items = [
                        {
                            "input_id": item["input_id"],
                            "transcript": item.get("transcript") or "",
                        }
                        for item in preprocessed["items"]
                        if item["type"] == "audio"
                    ]
                    if audio_items:
                        st.session_state.diary_pending_audio = {
                            "prompt": prompt,
                            "input_ids": input_ids,
                            "audio_items": audio_items,
                        }
                        st.session_state.diary_audio_editing = False
                        st.rerun()
                send_prepared_turn(prompt, input_ids)
            st.rerun()
        except Exception as exc:
            st.error(f"챗봇 호출 실패: {exc}")

if st.session_state.diary_ready and st.session_state.diary_result is None:
    st.success("일기를 만들 정보가 준비됐습니다.")
    if st.button("오늘의 일기 후보 생성", type="primary"):
        try:
            job = request_generation(st.session_state.diary_session_id)
            with st.spinner("HCX-007이 오늘의 일기 후보를 작성하고 있어요..."):
                for _ in range(60):
                    status = get_job(job["job_id"])
                    if status["status"] == "completed":
                        st.session_state.diary_result = status["result"]
                        st.session_state.diary_versions = list_versions(
                            st.session_state.diary_session_id
                        )["versions"]
                        st.session_state.diary_show_versions = False
                        break
                    if status["status"] == "failed":
                        raise RuntimeError(status.get("error_code") or "generation failed")
                    time.sleep(0.5)
                else:
                    raise TimeoutError("일기 생성 시간이 초과됐습니다.")
            st.rerun()
        except Exception as exc:
            st.error(f"일기 후보 생성 실패: {exc}")

if st.session_state.diary_result:
    result = st.session_state.diary_result
    st.divider()
    st.subheader(result["title"])
    for paragraph in result["paragraphs"]:
        st.write(paragraph)
    if result.get("emotion_tags"):
        st.caption("감정 태그: " + ", ".join(result["emotion_tags"]))

    if result.get("approved"):
        st.success("오늘의 일기로 확정됐어요.")
    else:
        st.info("아직 후보 상태예요. 후보를 비교한 뒤 하나를 확정해 주세요.")

    script_result = st.session_state.diary_script_result
    if result.get("approved") and script_result:
        st.markdown("#### 🎙️ 나레이션 대본")
        st.write(script_result["narration_text"])
        if script_result.get("audio_url"):
            st.audio(script_result["audio_url"])
        st.caption(
            f"예상 길이: {script_result['target_duration_seconds']}초 · "
            f"대표 감정: {script_result['emotion']}"
        )
    elif result.get("approved"):
        st.warning("나레이션 대본을 아직 생성하지 못했습니다.")
        if st.button("나레이션 대본 다시 생성"):
            try:
                with st.spinner("나레이션 대본을 작성하고 있어요..."):
                    retry = approve_version(
                        st.session_state.diary_session_id,
                        result["version_id"],
                    )
                    st.session_state.diary_script_result = wait_for_generation(
                        {"job_id": retry["media_job_id"]}
                    )
                st.rerun()
            except Exception as exc:
                st.error(f"나레이션 대본 생성 실패: {exc}")

if st.session_state.diary_show_versions:
    show_version_picker()
