import streamlit as st
import pandas as pd
import numpy as np

# Configuración de la página
st.set_page_config(page_title="Reporte Abandonos", layout="wide")
st.title("✈️ Generador de Reporte: Detalle Pasajeros Abandonos")

# =============================================================================
# FUNCIONES DE CACHÉ (LA CLAVE DE LA VELOCIDAD)
# =============================================================================

@st.cache_data(show_spinner=False)
def load_data(file_master, file_reservas, files_transacciones):
    """
    Carga y procesa los datos. Al usar cache, esto solo se ejecuta
    cuando cambian los archivos subidos.
    """
    
    # 1. Carga Master
    # -----------------------------------------------------
    if file_master.name.endswith('.csv'):
        df_master = pd.read_csv(file_master)
    else:
        df_master = pd.read_excel(file_master)
    
    # 2. Carga Reservas (Detectando separador)
    # -----------------------------------------------------
    try:
        df_reservas = pd.read_csv(file_reservas, sep=';')
        if len(df_reservas.columns) < 2: 
            file_reservas.seek(0)
            df_reservas = pd.read_csv(file_reservas, sep=',')
    except:
        file_reservas.seek(0)
        df_reservas = pd.read_csv(file_reservas, sep=',')

    # 3. Carga Transacciones (Múltiples archivos)
    # -----------------------------------------------------
    df_list = []
    if files_transacciones:
        for f in files_transacciones:
            try:
                temp = pd.read_csv(f, engine='python') # engine python es más robusto
                df_list.append(temp)
            except Exception as e:
                st.warning(f"No se pudo leer {f.name}: {e}")
        
        if df_list:
            df_transacciones = pd.concat(df_list, ignore_index=True)
        else:
            df_transacciones = pd.DataFrame()
    else:
        df_transacciones = pd.DataFrame(columns=['Id Reserva', 'Modo', 'F.Desde Aerop', 'F.Hacia Aerop'])

    return df_master, df_reservas, df_transacciones

def clean_id(x):
    if pd.isna(x): return np.nan
    s = str(x).strip()
    if s.endswith('.0'): return s[:-2]
    return s

def clean_date_spanish(s):
    if pd.isna(s) or str(s).strip() == "": return pd.NaT
    s = str(s).strip().lower().replace(',', '').replace('.', '')
    s = s.replace('p m', 'pm').replace('a m', 'am')
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.NaT

# =============================================================================
# INTERFAZ DE USUARIO
# =============================================================================

st.sidebar.header("📂 Carga de Archivos")

uploaded_master = st.sidebar.file_uploader("1. Máster Compensaciones (.xlsx/.csv)", type=['xlsx', 'csv'])
uploaded_reservas = st.sidebar.file_uploader("2. Detalle Reservas (.csv)", type=['csv'])
uploaded_trans = st.sidebar.file_uploader("3. Transacciones (.csv)", type=['csv'], accept_multiple_files=True)

if uploaded_master and uploaded_reservas:
    
    if st.button("🚀 Generar Reporte"):
        
        with st.spinner('Procesando datos...'):
            # 1. CARGA (Con Cache)
            df_master, df_reservas, df_trans = load_data(uploaded_master, uploaded_reservas, uploaded_trans)
            
            progress_bar = st.progress(0)
            status_text = st.empty()

            # 2. LIMPIEZA
            status_text.text("Normalizando IDs...")
            df_master['id_key'] = df_master['id_reserva'].apply(clean_id)
            df_reservas['id_key'] = df_reservas['id_reservation_id'].apply(clean_id)
            
            if not df_trans.empty and 'Id Reserva' in df_trans.columns:
                df_trans['id_key'] = df_trans['Id Reserva'].apply(clean_id)
            else:
                df_trans['id_key'] = np.nan
            
            progress_bar.progress(30)
            
            # 3. FECHAS
            status_text.text("Analizando fechas (formato español)...")
            df_reservas['tm_start_dt'] = pd.to_datetime(df_reservas['tm_start_local_at'], dayfirst=True, errors='coerce')
            
            if not df_trans.empty:
                # Optimizacion: Vectorizar limpieza básica antes de apply si es posible, 
                # pero el apply aquí es seguro porque está cacheado si no cambia el input.
                df_trans['F.Desde Aerop_dt'] = df_trans['F.Desde Aerop'].apply(clean_date_spanish)
                df_trans['F.Hacia Aerop_dt'] = df_trans['F.Hacia Aerop'].apply(clean_date_spanish)
            else:
                df_trans['F.Desde Aerop_dt'] = pd.NaT
                df_trans['F.Hacia Aerop_dt'] = pd.NaT
                df_trans['Modo'] = np.nan

            progress_bar.progress(50)

            # 4. MERGE
            status_text.text("Cruzando bases de datos...")
            merged = pd.merge(df_master, df_reservas[['id_key', 'tm_start_dt']], on='id_key', how='left')
            merged = pd.merge(merged, df_trans[['id_key', 'Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt']], on='id_key', how='left')
            
            progress_bar.progress(70)

            # 5. LÓGICA DE NEGOCIO (OPTIMIZADA CON NUMPY - VECTORIZACIÓN)
            # Esto es mucho más rápido que .apply(axis=1)
            status_text.text("Calculando lógica de negocio...")
            
            # Condiciones para numpy.select
            # C1: Existe fecha en Reservas Journey
            c1 = merged['tm_start_dt'].notna()
            
            # C2: No existe Modo (no cruzó con Transacciones) -> NaT
            c2 = merged['Modo'].isna()
            
            # C3: Modo Round o ambas fechas existen -> Manual
            c3 = (merged['Modo'] == 'Round') | (merged['F.Desde Aerop_dt'].notna() & merged['F.Hacia Aerop_dt'].notna())
            
            # C4: Existe Desde
            c4 = merged['F.Desde Aerop_dt'].notna()
            
            # C5: Existe Hacia
            c5 = merged['F.Hacia Aerop_dt'].notna()

            # Definición de valores resultantes en orden de prioridad
            # Nota: np.select requiere que todos los outputs sean del mismo tipo.
            # Convertiremos todo a string temporalmente para manejar "Ingresar Manualmente" mezclado con fechas.
            
            merged['Calc_Temp'] = np.select(
                [c1, c2, c3, c4, c5], 
                [
                    merged['tm_start_dt'],          # Prioridad 1
                    pd.NaT,                         # Prioridad 2 (Vacío)
                    "Ingresar Manualmente",         # Prioridad 3
                    merged['F.Desde Aerop_dt'],     # Prioridad 4
                    merged['F.Hacia Aerop_dt']      # Prioridad 5
                ], 
                default=pd.NaT
            )

            progress_bar.progress(90)

            # 6. FORMATO FINAL
            status_text.text("Formateando salida...")
            
            def format_output_date(val):
                if isinstance(val, str): return val # "Ingresar Manualmente"
                if pd.isna(val): return ""
                return val.strftime('%d/%m/%Y')

            def format_output_hour(val):
                if isinstance(val, str) or pd.isna(val): return ""
                return val.hour
            
            def format_output_full(val):
                if isinstance(val, str): return val
                if pd.isna(val): return ""
                return val.strftime('%d/%m/%Y %H:%M:%S')

            merged['Fecha'] = merged['Calc_Temp'].apply(format_output_date)
            merged['Hora'] = merged['Calc_Temp'].apply(format_output_hour)
            merged['Tm_start_local_at'] = merged['Calc_Temp'].apply(format_output_full)

            # Columnas finales
            final_cols = {
                'Fecha_x': 'Datetime Compensación',
                'Dirección de correo electrónico': 'Dirección de correo electrónico',
                'Numero': 'Numero',
                'Correo registrado en Cabify para realizar la carga': 'Correo registrado en Cabify para realizar la carga',
                'Total Compensación': 'Monto a compensar',
                'Motivo compensación': 'Motivo compensación',
                'id_reserva': 'Id_reserva',
                'Clasificación': 'Compensación Aeropuerto',
                'Tm_start_local_at': 'Tm_start_local_at',
                'Fecha': 'Fecha',
                'Hora': 'Hora'
            }
            
            # Manejo de nombres de columna (Fecha_x vs Fecha)
            if 'Fecha' in merged.columns and 'Fecha_x' not in merged.columns and 'Datetime Compensación' not in merged.columns:
                 # Si Pandas no renombró Fecha a Fecha_x, buscamos la original
                 if 'Fecha_y' in merged.columns: # Significa que la original se llama Fecha_x
                     pass
                 else:
                     # Intentar encontrar la columna fecha original del master
                     final_cols['Fecha'] = 'Fecha_Calculada' # Renombramos nuestra calculada para no chocar
                     merged.rename(columns={'Fecha': 'Fecha_Calculada'}, inplace=True)
                     # Asumimos que la fecha master sigue llamándose Fecha o Fecha_x

            # Renombrar seguro
            available_cols = []
            for k, v in final_cols.items():
                if k in merged.columns:
                    merged.rename(columns={k: v}, inplace=True)
                    available_cols.append(v)
                elif k == 'Fecha_x' and 'Fecha' in merged.columns: 
                     # Caso borde
                     merged.rename(columns={'Fecha': 'Datetime Compensación'}, inplace=True)
                     available_cols.append('Datetime Compensación')

            output_df = merged[available_cols]

            progress_bar.progress(100)
            status_text.success("✅ ¡Reporte generado exitosamente!")
            
            # VISTA PREVIA
            st.dataframe(output_df.head(10))
            
            # BOTÓN DE DESCARGA
            csv = output_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte Completo",
                data=csv,
                file_name="Detalle_Pasajeros_Abandonos.csv",
                mime="text/csv"
            )

else:
    st.info("👋 Por favor carga los archivos 'Master' y 'Reservas' en el menú lateral para comenzar.")
