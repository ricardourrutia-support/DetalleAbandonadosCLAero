import streamlit as st
import pandas as pd
import numpy as np
import io
import xlsxwriter

# =============================================================================
# CONFIGURACIÓN DE PÁGINA Y ESTILOS
# =============================================================================
st.set_page_config(page_title="Reporte Abandonos Cabify", layout="wide", page_icon="✈️")

st.markdown("""
<style>
    .main-header {font-size: 2.5rem; color: #7145D6; font-weight: bold;}
    .sub-header {font-size: 1.5rem; color: #5B34AC;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-header">✈️ Generador de Reporte: Detalle Pasajeros Abandonos</p>', unsafe_allow_html=True)
st.markdown("Herramienta oficial para consolidación de compensaciones y reservas abandonadas.")

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def clean_id_strict(x):
    """Limpia IDs y retorna NaN si no son válidos."""
    if pd.isna(x): return np.nan
    s = str(x).strip()
    if len(s) > 20 or not s.replace('.', '').isdigit(): return np.nan
    if s.endswith('.0'): return s[:-2]
    return s

def clean_date_spanish(s):
    """Parsea fechas complejas en español."""
    if pd.isna(s) or str(s).strip() == "": return pd.NaT
    s = str(s).strip().lower().replace(',', '').replace('.', '')
    s = s.replace('p m', 'pm').replace('a m', 'am')
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.NaT

def to_excel_cabify(df):
    """
    Genera un archivo Excel con estilos corporativos de Cabify.
    Retorna el objeto BytesIO listo para descargar.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
        
        workbook = writer.book
        worksheet = writer.sheets['Reporte']
        
        # --- DEFINICIÓN DE COLORES CABIFY ---
        cabify_purple = '#7145D6'  # Morado principal
        cabify_light = '#F5F1FC'   # Fondo claro para alternancia (opcional)
        text_white = '#FFFFFF'
        
        # --- FORMATOS ---
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': cabify_purple,
            'font_color': text_white,
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 11
        })
        
        cell_format = workbook.add_format({
            'font_name': 'Calibri',
            'font_size': 10,
            'valign': 'vcenter',
            'border': 1,
            'border_color': '#E0E0E0'
        })
        
        # Aplicar formato a los datos (todo el rango)
        worksheet.set_column(0, len(df.columns) - 1, 20, cell_format)
        
        # Aplicar formato a los encabezados
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            
            # Ajuste inteligente de ancho de columna
            # Basado en la longitud del encabezado o un ancho fijo razonable
            col_len = max(len(str(value)) + 2, 15) 
            worksheet.set_column(col_num, col_num, col_len)

    return output.getvalue()

# =============================================================================
# CARGA DE DATOS (CON CACHÉ)
# =============================================================================

@st.cache_data(show_spinner=False)
def load_data_cached(file_master, file_reservas, files_transacciones):
    # 1. Master
    if file_master.name.endswith('.csv'):
        df_master = pd.read_csv(file_master)
    else:
        df_master = pd.read_excel(file_master)
        
    # 2. Reservas
    try:
        df_reservas = pd.read_csv(file_reservas, sep=';')
        if len(df_reservas.columns) < 2: 
            file_reservas.seek(0)
            df_reservas = pd.read_csv(file_reservas, sep=',')
    except:
        file_reservas.seek(0)
        df_reservas = pd.read_csv(file_reservas, sep=',')
        
    # 3. Transacciones
    df_list = []
    if files_transacciones:
        for f in files_transacciones:
            try:
                temp = pd.read_csv(f, engine='python')
                df_list.append(temp)
            except:
                pass
        df_trans = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
    else:
        df_trans = pd.DataFrame(columns=['Id Reserva', 'Modo', 'F.Desde Aerop', 'F.Hacia Aerop'])
        
    return df_master, df_reservas, df_trans

# =============================================================================
# LÓGICA PRINCIPAL DE LA APP
# =============================================================================

st.sidebar.header("📂 1. Inputs Principales")
uploaded_master = st.sidebar.file_uploader("Máster Compensaciones", type=['xlsx', 'csv'])
uploaded_reservas = st.sidebar.file_uploader("Detalle Reservas", type=['csv'])
uploaded_trans = st.sidebar.file_uploader("Transacciones (Opcional)", type=['csv'], accept_multiple_files=True)

st.sidebar.markdown("---")
st.sidebar.header("📂 2. Histórico (Opcional)")
uploaded_history = st.sidebar.file_uploader("Cargar reporte anterior para filtrar nuevos", type=['csv', 'xlsx'])

if uploaded_master and uploaded_reservas:
    if st.button("🚀 Procesar Reporte"):
        
        with st.spinner('Cruzando bases de datos y aplicando estilos...'):
            # --- 1. PROCESAMIENTO ---
            df_master, df_reservas, df_trans = load_data_cached(uploaded_master, uploaded_reservas, uploaded_trans)
            
            # Limpieza Master
            if 'Fecha' in df_master.columns: 
                df_master.rename(columns={'Fecha': 'Datetime Compensación'}, inplace=True)
            
            # Filtro Motivos
            if 'Motivo compensación' in df_master.columns:
                motivos = ["usuario pierde el vuelo", "reserva no encuentra conductor o no llega el conductor"]
                mask = df_master['Motivo compensación'].astype(str).str.strip().str.lower().isin(motivos)
                df_master = df_master[mask].copy()

            # ID Master
            col_id_m = 'id_reserva' if 'id_reserva' in df_master.columns else [c for c in df_master.columns if 'id_reserva' in c.lower()][0]
            df_master['id_key'] = pd.to_numeric(df_master[col_id_m], errors='coerce')
            df_master.dropna(subset=['id_key'], inplace=True)
            df_master['id_key'] = df_master['id_key'].astype(str).str.replace(r'\.0$', '', regex=True)
            
            # Preparar Secundarias
            col_id_r = 'id_reservation_id' if 'id_reservation_id' in df_reservas.columns else df_reservas.columns[1]
            df_reservas['id_key'] = df_reservas[col_id_r].apply(clean_id_strict)
            df_reservas['tm_start_dt'] = pd.to_datetime(df_reservas['tm_start_local_at'], dayfirst=True, errors='coerce')
            
            if not df_trans.empty and 'Id Reserva' in df_trans.columns:
                df_trans['id_key'] = df_trans['Id Reserva'].apply(clean_id_strict)
                df_trans['F.Desde Aerop_dt'] = df_trans['F.Desde Aerop'].apply(clean_date_spanish) if 'F.Desde Aerop' in df_trans.columns else pd.NaT
                df_trans['F.Hacia Aerop_dt'] = df_trans['F.Hacia Aerop'].apply(clean_date_spanish) if 'F.Hacia Aerop' in df_trans.columns else pd.NaT
            else:
                for c in ['id_key','F.Desde Aerop_dt','F.Hacia Aerop_dt','Modo']: df_trans[c] = np.nan if c == 'Modo' else pd.NaT

            # Cruces
            merged = pd.merge(df_master, df_reservas[['id_key', 'tm_start_dt']], on='id_key', how='left')
            cols_t = [c for c in ['id_key', 'Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt'] if c in df_trans.columns]
            merged = pd.merge(merged, df_trans[cols_t], on='id_key', how='left')
            
            # Vectorización Lógica Fechas
            for c in ['Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt']: 
                if c not in merged.columns: merged[c] = np.nan
            
            c1 = merged['tm_start_dt'].notna()
            c2 = merged['Modo'].isna()
            c3 = (merged['Modo'] == 'Round') | (merged['F.Desde Aerop_dt'].notna() & merged['F.Hacia Aerop_dt'].notna())
            c4 = merged['F.Desde Aerop_dt'].notna()
            c5 = merged['F.Hacia Aerop_dt'].notna()
            
            merged['Calc_Temp'] = np.select(
                [c1, c2, c3, c4, c5],
                [merged['tm_start_dt'].astype(object), pd.NaT, "Ingresar Manualmente", merged['F.Desde Aerop_dt'].astype(object), merged['F.Hacia Aerop_dt'].astype(object)],
                default=pd.NaT
            )

            # Formato
            def fmt_d(v): return v.strftime('%d/%m/%Y') if (pd.notna(v) and not isinstance(v, str)) else ("" if pd.isna(v) else v)
            def fmt_h(v): return v.hour if (pd.notna(v) and not isinstance(v, str)) else ""
            def fmt_f(v): return v.strftime('%d/%m/%Y %H:%M:%S') if (pd.notna(v) and not isinstance(v, str)) else ("" if pd.isna(v) else v)

            merged['Fecha_Viaje'] = merged['Calc_Temp'].apply(fmt_d)
            merged['Hora_Viaje'] = merged['Calc_Temp'].apply(fmt_h)
            merged['Tm_Final'] = merged['Calc_Temp'].apply(fmt_f)

            # Selección Final
            final_cols = {
                'Datetime Compensación': 'Datetime Compensación',
                'Dirección de correo electrónico': 'Dirección de correo electrónico',
                'Numero': 'Numero',
                'Correo registrado en Cabify para realizar la carga': 'Correo registrado en Cabify para realizar la carga',
                'Total Compensación': 'Monto a compensar',
                'Motivo compensación': 'Motivo compensación',
                'id_reserva': 'Id_reserva',
                'Clasificación': 'Compensación Aeropuerto',
                'Tm_Final': 'Tm_start_local_at',
                'Fecha_Viaje': 'Fecha',
                'Hora_Viaje': 'Hora'
            }
            
            df_full = pd.DataFrame()
            for src, dst in final_cols.items():
                df_full[dst] = merged[src] if src in merged.columns else ""

            # --- 2. LÓGICA INCREMENTAL (NUEVOS) ---
            df_new = None
            if uploaded_history:
                try:
                    if uploaded_history.name.endswith('.csv'):
                        df_hist = pd.read_csv(uploaded_history)
                    else:
                        df_hist = pd.read_excel(uploaded_history)
                        
                    if 'Numero' in df_hist.columns and 'Numero' in df_full.columns:
                        ids_old = df_hist['Numero'].astype(str).unique()
                        ids_curr = df_full['Numero'].astype(str)
                        df_new = df_full[~ids_curr.isin(ids_old)]
                except:
                    st.error("Error procesando histórico.")

            # --- 3. DISPLAY Y DESCARGA (EXCEL) ---
            st.success(f"✅ Procesamiento Exitoso. Filas Totales: {len(df_full)}")
            
            tab1, tab2 = st.tabs(["📊 Reporte Completo", "🆕 Solo Nuevos"])
            
            with tab1:
                st.dataframe(df_full.head())
                excel_data = to_excel_cabify(df_full)
                st.download_button(
                    label="📥 Descargar Excel (Estilo Cabify)",
                    data=excel_data,
                    file_name="Detalle_Pasajeros_Abandonos_FULL.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            with tab2:
                if uploaded_history:
                    if df_new is not None and not df_new.empty:
                        st.info(f"Se encontraron {len(df_new)} registros nuevos.")
                        st.dataframe(df_new.head())
                        excel_new = to_excel_cabify(df_new)
                        st.download_button(
                            label="📥 Descargar Excel Nuevos (Estilo Cabify)",
                            data=excel_new,
                            file_name="Detalle_Pasajeros_Abandonos_NUEVOS.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.warning("No hay registros nuevos comparado con el histórico.")
                else:
                    st.info("Sube un archivo histórico en el panel lateral para ver esta sección.")

else:
    st.info("👋 Sube los archivos requeridos para comenzar.")
