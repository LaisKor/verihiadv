import streamlit as st
import database
from datetime import date
import time
import pandas as pd

st.set_page_config(page_title="베리하이 통합 시스템", layout="wide")
database.init_db()

# 세션 상태 관리
if "clear_input" in st.session_state and st.session_state.clear_input:
    for key in ["m_no_input", "ro_input", "p_no_input"]: st.session_state[key] = ""
    st.session_state.clear_input = False
if "scanned_barcodes" not in st.session_state: st.session_state.scanned_barcodes = []

def load_bsa():
    df_raw = database.get_all_bsa()
    cols = ['ID', '관리번호', '재제조번호', '고객사', '차종', '품번', 'RO번호', '보증구분', '상태', '입고일', '세척사진경로']
    if not df_raw.empty and len(df_raw.columns) == 11:
        df_raw.columns = cols
        return df_raw
    return pd.DataFrame(columns=cols)

df = load_bsa()

# '대메뉴' -> '메뉴'로 명칭 변경
st.sidebar.title("⭐ 베리하이 시스템")
main_menu = st.sidebar.selectbox("메뉴", ["🏭 공정 관리(BSA)", "📦 자재 입고/재고", "📋 이력 관리"])

# ---------------------------------------------------------
# 🏭 공정 관리 (대시보드 기능 강화)
# ---------------------------------------------------------
if main_menu == "🏭 공정 관리(BSA)":
    sub_menu = st.sidebar.radio("공정 단계", ["📊 통합 대시보드", "📥 입고 등록", "🧼 세척", "🔧 분해 조립", "🧪 성능검사", "📟 EOL", "🚚 출하검사"])
    
    if sub_menu == "📊 통합 대시보드":
        st.title("📊 공정별 실시간 대시보드")
        
        # 상단 핵심 지표 (Metric)
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("입고대기", len(df[df['상태']=='입고']))
        m2.metric("세척완료", len(df[df['상태']=='세척완료']))
        m3.metric("조립완료", len(df[df['상태']=='분해조립완료']))
        m4.metric("성능합격", len(df[df['상태']=='성능검사OK']))
        m5.metric("EOL완료", len(df[df['상태']=='EOL완료']))
        m6.metric("출하승인", len(df[df['상태']=='출하검사OK']))
        
        st.divider()

        # 공정별 상세 대시보드 (Expander로 리스트 분리)
        st.subheader("🔎 단계별 상세 리스트")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            with st.expander("📥 입고/세척 대기", expanded=True):
                st.dataframe(df[df['상태']=='입고'][['관리번호', '차종', '입고일']], use_container_width=True, hide_index=True)
        with c2:
            with st.expander("🧼 세척완료/조립대기", expanded=True):
                st.dataframe(df[df['상태']=='세척완료'][['관리번호', '차종']], use_container_width=True, hide_index=True)
        with c3:
            with st.expander("🔧 조립완료/검사대기", expanded=True):
                st.dataframe(df[df['상태']=='분해조립완료'][['관리번호', '차종']], use_container_width=True, hide_index=True)

        c4, c5, c6 = st.columns(3)
        with c4:
            with st.expander("🧪 성능검사 합격", expanded=False):
                st.dataframe(df[df['상태']=='성능검사OK'][['관리번호', '차종']], use_container_width=True, hide_index=True)
        with c5:
            with st.expander("📟 EOL 테스트 완료", expanded=False):
                st.dataframe(df[df['상태']=='EOL완료'][['관리번호', '차종']], use_container_width=True, hide_index=True)
        with c6:
            with st.expander("🚚 출하 검사 합격", expanded=False):
                st.dataframe(df[df['상태']=='출하검사OK'][['관리번호', '차종']], use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📋 전체 공정 마스터 데이터")
        st.dataframe(df, use_container_width=True, hide_index=True)

    # (이후 입고 등록, 세척, 분해 조립 등의 로직은 이전과 동일하게 유지)
    elif sub_menu == "📥 입고 등록":
        st.title("📥 신규 BSA 입고 등록")
        next_no = database.get_next_reman_no()
        with st.container(border=True):
            c1, c2 = st.columns(2)
            m_no = c1.text_input("관리번호 (S/N)", key="m_no_input")
            cust = c1.selectbox("고객사", ["기아", "현대", "기타"], key="cust_input")
            ro_no = c1.text_input("R/O 번호", key="ro_input")
            model = c2.text_input("차종", value="PU_EV", key="model_input")
            p_no = c2.text_input("품번", key="p_no_input")
            w_type = c2.radio("보증 구분", ["일반", "보증"], horizontal=True, key="w_type_input")
            if st.button("📥 입고 완료", type="primary"):
                if m_no.strip():
                    res, msg = database.insert_bsa({"manage_no":m_no, "reman_no":next_no, "customer":cust, "car_model":model, "part_no":p_no, "ro_no":ro_no, "warranty_type":w_type, "inbound_date":date.today().isoformat()})
                    if res: st.success("✅ 등록되었습니다."); st.session_state.clear_input=True; time.sleep(1); st.rerun()
                    else: st.error(msg)

    elif sub_menu == "🧼 세척":
        st.title("🧼 세척 공정")
        items = df[df['상태']=='입고']['관리번호'].tolist()
        if items:
            target = st.selectbox("대상 선택", items)
            photo = st.file_uploader("세척 후 사진 첨부", type=['jpg', 'png', 'jpeg'])
            if st.button("🧼 세척 완료 처리"):
                path = database.save_photo(target, photo) if photo else None
                database.update_bsa_status(target, "세척완료", path)
                st.success("✅ 세척 완료"); time.sleep(1); st.rerun()
        else: st.info("세척 대기 중인 항목이 없습니다.")

    elif sub_menu == "🔧 분해 조립":
        st.title("🔧 분해 조립 및 자재 일괄 투입")
        items = df[df['상태']=='세척완료']['관리번호'].tolist()
        if items:
            with st.container(border=True):
                target = st.selectbox("대상 BSA 선택", items)
                parts_list = ["CMU", "BMA", "BMU", "UPR/C", "LWR/C", "W/H", "LV_W/H"]
                final_usage_list = []
                cols = st.columns(2)
                for i, p_type in enumerate(parts_list):
                    with cols[i % 2]:
                        with st.expander(f"🔹 {p_type} 교체", expanded=False):
                            n_b = st.text_input(f"{p_type} 신규 S/N", key=f"new_{p_type}")
                            o_b = st.text_input(f"{p_type} 탈거 S/N", key=f"old_{p_type}")
                            if n_b:
                                info = database.get_part_info_by_barcode(n_b)
                                if info:
                                    if p_type.upper() in info[0].upper() or p_type.upper() in info[1].upper():
                                        stock_qty = database.get_part_stock_qty(n_b)
                                        if stock_qty > 0:
                                            st.success(f"✅ 재고: {stock_qty}개")
                                            if o_b: final_usage_list.append({"type": p_type, "new": n_b, "old": o_b})
                                        else: st.error("🚨 재고 없음")
                                    else: st.error("🚨 종류 불일치")
                                else: st.error("🚨 미등록")
                if st.button("🔧 일괄 조립 완료 확정", type="primary", use_container_width=True):
                    if final_usage_list:
                        database.record_multiple_usages(target, final_usage_list)
                        st.success("✅ 공정 완료!"); time.sleep(1.5); st.rerun()
        else: st.info("조립 대기 중인 항목이 없습니다.")

    elif sub_menu in ["🧪 성능검사", "📟 EOL", "🚚 출하검사"]:
        mapping = {"🧪 성능검사": ("분해조립완료", "성능검사OK"), "📟 EOL": ("성능검사OK", "EOL완료"), "🚚 출하검사": ("EOL완료", "출하검사OK")}
        p_status, n_status = mapping[sub_menu]
        st.title(sub_menu)
        items = df[df['상태']==p_status]['관리번호'].tolist()
        if items:
            target = st.selectbox("대상 선택", items)
            if st.button(f"{sub_menu} 완료"):
                database.update_bsa_status(target, n_status)
                st.success("공정 통과"); time.sleep(1); st.rerun()
        else: st.info("해당 단계 대상 없음")

# ---------------------------------------------------------
# 📦 자재 관리 / 📋 이력 관리
# ---------------------------------------------------------
elif main_menu == "📦 자재 입고/재고":
    sub_tab = st.sidebar.radio("자재 메뉴", ["📊 재고 및 추적 현황", "📥 신규 자재 입고"])
    if sub_tab == "📊 재고 및 추적 현황":
        st.title("📊 자재 추적 대시보드")
        query = """SELECT m.barcode, m.part_name, m.part_type, m.from_bsa, m.to_bsa, s.current_qty 
                   FROM parts_master m LEFT JOIN parts_stock s ON m.barcode = s.barcode"""
        with database.get_connection() as conn: stock_df = pd.read_sql_query(query, conn)
        t1, t2, t3 = st.tabs(["🆕 신품", "♻️ 고품", "🗑️ 폐기품"])
        with t1: st.dataframe(stock_df[stock_df['part_type']=='신품'], use_container_width=True, hide_index=True)
        with t2: st.dataframe(stock_df[stock_df['part_type']=='고품'], use_container_width=True, hide_index=True)
        with t3: st.dataframe(stock_df[stock_df['part_type']=='폐기품'], use_container_width=True, hide_index=True)

    elif sub_tab == "📥 신규 자재 입고":
        st.title("📥 자재 신규 입고")
        scan_in = st.text_input("바코드 스캔", key="scan_box")
        preset = database.get_part_info_by_barcode(scan_in) if scan_in else None
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            p_type = c1.selectbox("성격", ["신품", "고품"], index=0 if not preset or preset[2]=="신품" else 1)
            origin = c2.selectbox("출처", ["일반", "보증"], index=0 if not preset or preset[3]=="일반" else 1)
            t_qty = c3.number_input("수량", min_value=1, value=1)
            p_no = st.text_input("품번", value=preset[1] if preset else "")
            p_name = st.text_input("품명", value=preset[0] if preset else "")
        if st.button("➕ 추가"):
            st.session_state.scanned_barcodes.append({"barcode": scan_in, "part_no": p_no, "part_name": p_name, "part_type": p_type, "origin": origin, "qty": t_qty, "location": "창고A"})
        if st.session_state.scanned_barcodes:
            st.table(pd.DataFrame(st.session_state.scanned_barcodes))
            if st.button("💾 저장"):
                database.register_and_inbound(st.session_state.scanned_barcodes)
                st.session_state.scanned_barcodes = []; st.success("저장 완료"); time.sleep(1); st.rerun()

elif main_menu == "📋 이력 관리":
    st.title("📋 통합 이력 관리")
    tab1, tab2 = st.tabs(["🏭 BSA 공정 현황", "🔍 부품 사용 이력"])
    with tab1: st.dataframe(df, use_container_width=True, hide_index=True)
    with tab2:
        with database.get_connection() as conn:
            trace_query = "SELECT * FROM part_usage ORDER BY id DESC"
            st.dataframe(pd.read_sql_query(trace_query, conn), use_container_width=True, hide_index=True)
