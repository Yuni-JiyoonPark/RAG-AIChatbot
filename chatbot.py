import os
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.vectorstores import FAISS
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document
import streamlit as st

# FAISS 인덱스 생성 및 로드 함수
def create_or_load_faiss_index(folder_path, faiss_file_path, chunk_size=1000, chunk_overlap=100):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embeddings = OpenAIEmbeddings()

    if os.path.exists(faiss_file_path):
        vector_store = FAISS.load_local(faiss_file_path, embeddings, allow_dangerous_deserialization=True)
    else:
        all_docs = []
        for root, _, files in os.walk(folder_path):
            for file_name in files:
                if file_name.endswith(".pdf"):
                    file_path = os.path.join(root, file_name)
                    loader = PyPDFLoader(file_path)
                    documents = loader.load()
                    docs = text_splitter.split_documents(documents)
                    all_docs.extend(docs)

        vector_store = FAISS.from_documents(all_docs, embeddings)
        vector_store.save_local(faiss_file_path)
    return vector_store

# QA 체인 및 프롬프트 설정 함수
def create_qa_chain():
    # OpenAI API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경 변수를 설정하거나 API 키를 제공해야 합니다.")

    # ChatOpenAI 초기화
    llm = ChatOpenAI(
        temperature=0,
        openai_api_key=api_key,       # OpenAI API 키
        model_name="gpt-4o",         # gpt-4o 모델 지정
        max_retries=3                # 최대 재시도 횟수
    )

    custom_prompt = PromptTemplate(
        input_variables=["context", "question", "history"],
        template=(
            "당신은 친절하고 전문적인 경제 전문가로서 사용자 질문에 답변하는 AI입니다. "
            "당신의 목표는 복잡한 경제 정보를 쉽게 설명하고, 상세하고 정확하며 실용적인 조언을 제공하는 것입니다.\n\n"
            "다음은 문서에서 추출한 관련 정보입니다:\n\n{context}\n\n"
            "이전에 나눈 대화는 다음과 같습니다:\n{history}\n\n"
            "위의 정보와 대화를 바탕으로, 아래 질문에 대해 경제 전문가로서 "
            "심층적이고 분석적인 답변을 작성해 주세요. "
            "가능한 경우, 구체적인 예시와 설명을 추가하고, 관련 배경 지식도 포함해 주세요.\n\n"
            "질문: {question}\n\n"
            "친절하고 분석적인 답변:"
        )
    )
    return create_stuff_documents_chain(llm, custom_prompt)

# 대화 기록 관리 클래스
class ConversationHistory:
    def __init__(self):
        self.history = []

    def add_entry(self, question, answer):
        self.history.append({"question": question, "answer": answer})

    def to_text(self):
        return "\n".join(
            [f"Q: {entry['question']}\nA: {entry['answer']}" for entry in self.history]
        )

# Streamlit에서 실행될 챗봇 UI
def show_chatbot():
    st.subheader("🤖 경제 전문가 AI 챗봇")

    folder_path = "./reports"
    faiss_file_path = "./faiss_index"

    if "history_manager" not in st.session_state:
        st.session_state.history_manager = ConversationHistory()

    if "qa_chain" not in st.session_state:
        st.session_state.qa_chain = create_qa_chain()

    if "vector_store" not in st.session_state:
        st.session_state.vector_store = create_or_load_faiss_index(folder_path, faiss_file_path)

    user_query = st.text_input("질문을 입력하세요:", "")

    if user_query:
        vector_store = st.session_state.vector_store
        qa_chain = st.session_state.qa_chain
        history_manager = st.session_state.history_manager

        try:
            retrieved_docs = vector_store.similarity_search(user_query, k=5)
            documents = [
                Document(
                    page_content=doc.page_content if hasattr(doc, 'page_content') else str(doc),
                    metadata=doc.metadata
                )
                for doc in retrieved_docs
            ]
            history_text = history_manager.to_text()
            response = qa_chain.invoke({
                "context": documents,
                "question": user_query,
                "history": history_text
            })
            history_manager.add_entry(user_query, response)
            st.session_state.history_manager = history_manager
        except Exception as e:
            response = f"오류 발생: {e}"

        st.write("### 챗봇 답변:")
        st.write(response)
