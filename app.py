import streamlit as st
import pandas as pd
import numpy as np
import io

# Configuración de la página
st.set_page_config(page_title="Reporte Abandonos", layout="wide")
st.title("✈️ Generador de Reporte: Detalle Pasajeros Abandonos")

# =============================================================================
# FUNCIONES DE CACHÉ
# =============================================================================

@st.cache_data(show_spinner=False)
def load_data(file_master, file_reservas, files_transacciones):
    """
    Carga los datos crudos. El filtrado se hace después para mayor control.
    """
    # 1. Carga Master
    if file_master.name.endswith('.csv'):
        df_master = pd.read_csv(file_master)
    else:
        df_master = pd.read_excel(file_master)
    
    # 2. Carga Reservas
    try:
        # Intentar con punto y coma primero (común en este reporte)
        df_reservas = pd.read_csv(file_reservas, sep=';')
        if len(df_reservas.columns) < 2: 
            file_reservas.seek(0)
            df_reservas = pd.read_csv(file_reservas, sep=',')
    except:
        file_reservas.seek(0)
        df_reservas = pd.read_csv(file_reservas, sep=',')

    # 3. Carga Transacciones
    df_list = []
    if files_transacciones:
        for f in files_transacciones:
            try:
                temp = pd.read_csv(f, engine='python')
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

def clean_id_strict(x):
    """
    Intenta convertir a string numérico limpio. 
    Devuelve NaN si no es un número válido.
    """
    if pd.isna(x): return np.nan
    s = str(x).strip()
    
    # Si es una URL o texto largo, devolver NaN
    if len(s) > 20 or not s.replace('.', '').isdigit():
        return np.nan
        
    if s.endswith('.0'): return s[:-2]
    return s

def clean_date_spanish(s):
    """Parsea fechas en español robustamente"""
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
uploaded_master = st.sidebar.file_uploader("1. Máster Compensaciones", type=['xlsx', 'csv'])
uploaded_reservas = st.sidebar.file_uploader("2. Detalle Reservas", type=['csv'])
uploaded_trans = st.sidebar.file_uploader("3. Transacciones", type=['csv'], accept_multiple_files=True)

if uploaded_master and uploaded_reservas:
    
    if st.button("🚀 Generar Reporte"):
        
        with st.spinner('Procesando datos...'):
            # 1. CARGA
            df_master, df_reservas, df_trans = load_data(uploaded_master, uploaded_reservas, uploaded_trans)
            
            progress_bar = st.progress(0)
            status_text = st.empty()

            # -----------------------------------------------------------------
            # 2. PRE-PROCESAMIENTO Y FILTRADO DEL MÁSTER (NUEVO)
            # -----------------------------------------------------------------
            status_text.text("Aplicando filtros y limpieza al Máster...")
            
            # A) Renombrar Fecha INMEDIATAMENTE para protegerla
            # Buscamos la columna que se llame 'Fecha'
            cols_master = df_master.columns
            if 'Fecha' in cols_master:
                df_master.rename(columns={'Fecha': 'Datetime Compensación'}, inplace=True)
            else:
                st.warning("⚠️ No se encontró la columna 'Fecha' en el Máster. Verifica el archivo.")

            # B) Filtrar por Motivos Específicos
            # Normalizamos a minúsculas para comparar seguro
            if 'Motivo compensación' in df_master.columns:
                motivos_validos = [
                    "usuario pierde el vuelo",
                    "reserva no encuentra conductor o no llega el conductor"
                ]
                
                # Crear máscara (filtro) insensible a mayúsculas/minúsculas y espacios
                mask_motivo = df_master['Motivo compensación'].astype(str).str.strip().str.lower().isin(motivos_validos)
                
                rows_before = len(df_master)
                df_master = df_master[mask_motivo].copy()
                rows_after = len(df_master)
                
                st.info(f"Filtro de Motivos aplicado: {rows_after} registros válidos (de {rows_before} originales).")
            else:
                st.error("No se encontró la columna 'Motivo compensación' en el Máster.")
                st.stop()

            # C) Limpieza estricta de ID Reserva
            col_id_master = 'id_reserva' # Asumimos nombre estándar
            if col_id_master not in df_master.columns:
                # Intentar buscar columna alternativa si no existe
                # A veces viene como 'id_reserva ' con espacio
                possible_cols = [c for c in df_master.columns if 'id_reserva' in c.lower()]
                if possible_cols:
                    col_id_master = possible_cols[0]
                else:
                    st.error("No se encontró columna de ID Reserva en el Máster.")
                    st.stop()

            # Aplicar limpieza: convierte texto/urls a NaN
            df_master['id_key'] = pd.to_numeric(df_master[col_id_master], errors='coerce')
            
            # Eliminar los que quedaron como NaN (vacíos o texto inválido)
            df_master = df_master.dropna(subset=['id_key'])
            
            # Convertir a string limpio (sin .0) para el cruce
            df_master['id_key'] = df_master['id_key'].astype(str).str.replace(r'\.0$', '', regex=True)

            progress_bar.progress(20)

            # -----------------------------------------------------------------
            # 3. PREPARACIÓN DE RESERVAS Y TRANSACCIONES
            # -----------------------------------------------------------------
            status_text.text("Preparando bases secundarias...")

            # Reservas
            col_id_res = 'id_reservation_id'
            if col_id_res not in df_reservas.columns:
                 # Fallback
                 col_id_res = df_reservas.columns[1] # Adivinanza educada si falla nombre
            
            df_reservas['id_key'] = df_reservas[col_id_res].apply(clean_id_strict)
            df_reservas['tm_start_dt'] = pd.to_datetime(df_reservas['tm_start_local_at'], dayfirst=True, errors='coerce')
            
            # Transacciones
            if not df_trans.empty and 'Id Reserva' in df_trans.columns:
                df_trans['id_key'] = df_trans['Id Reserva'].apply(clean_id_strict)
                
                # Limpieza segura de fechas
                if 'F.Desde Aerop' in df_trans.columns:
                    df_trans['F.Desde Aerop_dt'] = df_trans['F.Desde Aerop'].apply(clean_date_spanish)
                else:
                    df_trans['F.Desde Aerop_dt'] = pd.NaT

                if 'F.Hacia Aerop' in df_trans.columns:
                    df_trans['F.Hacia Aerop_dt'] = df_trans['F.Hacia Aerop'].apply(clean_date_spanish)
                else:
                    df_trans['F.Hacia Aerop_dt'] = pd.NaT
            else:
                df_trans['id_key'] = np.nan
                df_trans['F.Desde Aerop_dt'] = pd.NaT
                df_trans['F.Hacia Aerop_dt'] = pd.NaT
                df_trans['Modo'] = np.nan

            progress_bar.progress(40)

            # -----------------------------------------------------------------
            # 4. CRUCES (MERGE)
            # -----------------------------------------------------------------
            status_text.text("Cruzando bases de datos...")
            
            # Cruce 1: Master filtrado + Reservas
            merged = pd.merge(df_master, df_reservas[['id_key', 'tm_start_dt']], on='id_key', how='left')
            
            # Cruce 2: + Transacciones
            cols_trans = ['id_key', 'Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt']
            cols_trans = [c for c in cols_trans if c in df_trans.columns]
            merged = pd.merge(merged, df_trans[cols_trans], on='id_key', how='left')
            
            progress_bar.progress(60)

            # -----------------------------------------------------------------
            # 5. CÁLCULO DE FECHA REAL (VECTORIZADO)
            # -----------------------------------------------------------------
            status_text.text("Calculando fechas reales de viaje...")

            # Asegurar columnas
            if 'Modo' not in merged.columns: merged['Modo'] = np.nan
            if 'F.Desde Aerop_dt' not in merged.columns: merged['F.Desde Aerop_dt'] = pd.NaT
            if 'F.Hacia Aerop_dt' not in merged.columns: merged['F.Hacia Aerop_dt'] = pd.NaT

            # Lógica
            c1 = merged['tm_start_dt'].notna()
            c2 = merged['Modo'].isna()
            c3 = (merged['Modo'] == 'Round') | (merged['F.Desde Aerop_dt'].notna() & merged['F.Hacia Aerop_dt'].notna())
            c4 = merged['F.Desde Aerop_dt'].notna()
            c5 = merged['F.Hacia Aerop_dt'].notna()

            # Cast a object para evitar TypeError en np.select
            val_1 = merged['tm_start_dt'].astype(object)
            val_2 = pd.NaT
            val_3 = "Ingresar Manualmente"
            val_4 = merged['F.Desde Aerop_dt'].astype(object)
            val_5 = merged['F.Hacia Aerop_dt'].astype(object)

            merged['Calc_Temp'] = np.select(
                [c1, c2, c3, c4, c5], 
                [val_1, val_2, val_3, val_4, val_5], 
                default=pd.NaT
            )

            progress_bar.progress(80)

            # -----------------------------------------------------------------
            # 6. FORMATO FINAL
            # -----------------------------------------------------------------
            status_text.text("Generando archivo final...")

            def format_output_date(val):
                if isinstance(val, str): return val 
                if pd.isna(val): return ""
                return val.strftime('%d/%m/%Y')

            def format_output_hour(val):
                if isinstance(val, str) or pd.isna(val): return ""
                return val.hour
            
            def format_output_full(val):
                if isinstance(val, str): return val
                if pd.isna(val): return ""
                return val.strftime('%d/%m/%Y %H:%M:%S')

            merged['Fecha_Viaje'] = merged['Calc_Temp'].apply(format_output_date)
            merged['Hora_Viaje'] = merged['Calc_Temp'].apply(format_output_hour)
            merged['Tm_Start_Final'] = merged['Calc_Temp'].apply(format_output_full)

            # Selección Final
            # Mapeo: Nombre en Dataframe -> Nombre en Reporte
            final_mapping = {
                'Datetime Compensación': 'Datetime Compensación', # Ya renombrado en paso 2A
                'Dirección de correo electrónico': 'Dirección de correo electrónico',
                'Numero': 'Numero',
                'Correo registrado en Cabify para realizar la carga': 'Correo registrado en Cabify para realizar la carga',
                'Total Compensación': 'Monto a compensar',
                'Motivo compensación': 'Motivo compensación',
                'id_reserva': 'Id_reserva', # Usamos el original para mostrar (o id_key si prefieres el limpio)
                'Clasificación': 'Compensación Aeropuerto',
                'Tm_Start_Final': 'Tm_start_local_at',
                'Fecha_Viaje': 'Fecha',
                'Hora_Viaje': 'Hora'
            }
            
            output_df = pd.DataFrame()
            for col_df, col_final in final_mapping.items():
                if col_df in merged.columns:
                    output_df[col_final] = merged[col_df]
                else:
                    output_df[col_final] = "" # Columna vacía si falta

            progress_bar.progress(100)
            status_text.success(f"✅ ¡Reporte generado! Se procesaron {len(output_df)} registros válidos.")

            # Vista Previa
            st.dataframe(output_df.head(10))

            # Descarga
            csv_buffer = io.BytesIO()
            output_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Descargar CSV Consolidado",
                data=csv_buffer.getvalue(),
                file_name="Detalle_Pasajeros_Abandonos.csv",
                mime="text/csv"
            )

else:
    st.info("👋 Sube los archivos requeridos en la barra lateral para comenzar.")
