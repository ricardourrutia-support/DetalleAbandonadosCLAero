import streamlit as st
import pandas as pd
import numpy as np
import io

# Configuración de la página
st.set_page_config(page_title="Reporte Abandonos", layout="wide")
st.title("✈️ Generador de Reporte: Detalle Pasajeros Abandonos")
st.markdown("""
Esta herramienta cruza el **Máster de Compensaciones** con **Reservas** y **Transacciones**.
Ahora permite subir un reporte anterior para identificar **solo los registros nuevos**.
""")

# =============================================================================
# FUNCIONES DE CACHÉ
# =============================================================================

@st.cache_data(show_spinner=False)
def load_data(file_master, file_reservas, files_transacciones):
    """
    Carga los datos crudos.
    """
    # 1. Carga Master
    if file_master.name.endswith('.csv'):
        df_master = pd.read_csv(file_master)
    else:
        df_master = pd.read_excel(file_master)
    
    # 2. Carga Reservas
    try:
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
    """Convierte a string numérico limpio. NaN si no es válido."""
    if pd.isna(x): return np.nan
    s = str(x).strip()
    if len(s) > 20 or not s.replace('.', '').isdigit(): return np.nan
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

st.sidebar.header("📂 1. Archivos Principales (Obligatorio)")
uploaded_master = st.sidebar.file_uploader("Máster Compensaciones", type=['xlsx', 'csv'])
uploaded_reservas = st.sidebar.file_uploader("Detalle Reservas", type=['csv'])
uploaded_trans = st.sidebar.file_uploader("Transacciones (Opcional)", type=['csv'], accept_multiple_files=True)

st.sidebar.markdown("---")
st.sidebar.header("📂 2. Histórico (Opcional)")
uploaded_history = st.sidebar.file_uploader("Cargar reporte anterior para filtrar nuevos", type=['csv'])

if uploaded_master and uploaded_reservas:
    
    if st.button("🚀 Procesar Reportes"):
        
        with st.spinner('Procesando datos...'):
            # -----------------------------------------------------------------
            # PASO 1: GENERACIÓN DEL REPORTE COMPLETO (Lógica anterior)
            # -----------------------------------------------------------------
            
            # Carga
            df_master, df_reservas, df_trans = load_data(uploaded_master, uploaded_reservas, uploaded_trans)
            progress_bar = st.progress(0)
            status_text = st.empty()

            # Pre-procesamiento Master
            status_text.text("Limpiando Máster...")
            if 'Fecha' in df_master.columns:
                df_master.rename(columns={'Fecha': 'Datetime Compensación'}, inplace=True)
            
            # Filtro Motivos
            if 'Motivo compensación' in df_master.columns:
                motivos_validos = ["usuario pierde el vuelo", "reserva no encuentra conductor o no llega el conductor"]
                mask_motivo = df_master['Motivo compensación'].astype(str).str.strip().str.lower().isin(motivos_validos)
                df_master = df_master[mask_motivo].copy()
            
            # Limpieza ID Master
            col_id_master = 'id_reserva'
            if col_id_master not in df_master.columns:
                 # Búsqueda fallback
                 possible = [c for c in df_master.columns if 'id_reserva' in c.lower()]
                 if possible: col_id_master = possible[0]
            
            df_master['id_key'] = pd.to_numeric(df_master[col_id_master], errors='coerce')
            df_master = df_master.dropna(subset=['id_key'])
            df_master['id_key'] = df_master['id_key'].astype(str).str.replace(r'\.0$', '', regex=True)

            progress_bar.progress(30)

            # Pre-procesamiento Bases Secundarias
            status_text.text("Preparando cruces...")
            col_id_res = 'id_reservation_id' if 'id_reservation_id' in df_reservas.columns else df_reservas.columns[1]
            df_reservas['id_key'] = df_reservas[col_id_res].apply(clean_id_strict)
            df_reservas['tm_start_dt'] = pd.to_datetime(df_reservas['tm_start_local_at'], dayfirst=True, errors='coerce')

            if not df_trans.empty and 'Id Reserva' in df_trans.columns:
                df_trans['id_key'] = df_trans['Id Reserva'].apply(clean_id_strict)
                df_trans['F.Desde Aerop_dt'] = df_trans['F.Desde Aerop'].apply(clean_date_spanish) if 'F.Desde Aerop' in df_trans.columns else pd.NaT
                df_trans['F.Hacia Aerop_dt'] = df_trans['F.Hacia Aerop'].apply(clean_date_spanish) if 'F.Hacia Aerop' in df_trans.columns else pd.NaT
            else:
                df_trans['id_key'] = np.nan; df_trans['F.Desde Aerop_dt'] = pd.NaT; df_trans['F.Hacia Aerop_dt'] = pd.NaT; df_trans['Modo'] = np.nan

            progress_bar.progress(50)

            # Cruces y Cálculo
            status_text.text("Calculando fechas...")
            merged = pd.merge(df_master, df_reservas[['id_key', 'tm_start_dt']], on='id_key', how='left')
            cols_trans = [c for c in ['id_key', 'Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt'] if c in df_trans.columns]
            merged = pd.merge(merged, df_trans[cols_trans], on='id_key', how='left')

            # Lógica Vectorizada
            for c in ['Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt']:
                if c not in merged.columns: merged[c] = np.nan if c == 'Modo' else pd.NaT

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

            # Formato Final
            def format_date(v): return v.strftime('%d/%m/%Y') if (not pd.isna(v) and not isinstance(v, str)) else (v if isinstance(v, str) else "")
            def format_hour(v): return v.hour if (not pd.isna(v) and not isinstance(v, str)) else ""
            def format_full(v): return v.strftime('%d/%m/%Y %H:%M:%S') if (not pd.isna(v) and not isinstance(v, str)) else (v if isinstance(v, str) else "")

            merged['Fecha_Viaje'] = merged['Calc_Temp'].apply(format_date)
            merged['Hora_Viaje'] = merged['Calc_Temp'].apply(format_hour)
            merged['Tm_Start_Final'] = merged['Calc_Temp'].apply(format_full)

            final_mapping = {
                'Datetime Compensación': 'Datetime Compensación',
                'Dirección de correo electrónico': 'Dirección de correo electrónico',
                'Numero': 'Numero',
                'Correo registrado en Cabify para realizar la carga': 'Correo registrado en Cabify para realizar la carga',
                'Total Compensación': 'Monto a compensar',
                'Motivo compensación': 'Motivo compensación',
                'id_reserva': 'Id_reserva',
                'Clasificación': 'Compensación Aeropuerto',
                'Tm_Start_Final': 'Tm_start_local_at',
                'Fecha_Viaje': 'Fecha',
                'Hora_Viaje': 'Hora'
            }
            
            df_full = pd.DataFrame()
            for col_df, col_final in final_mapping.items():
                df_full[col_final] = merged[col_df] if col_df in merged.columns else ""

            progress_bar.progress(80)

            # -----------------------------------------------------------------
            # PASO 2: LÓGICA INCREMENTAL (Solo Nuevos)
            # -----------------------------------------------------------------
            status_text.text("Verificando histórico...")
            df_new_only = None
            
            if uploaded_history is not None:
                try:
                    df_history = pd.read_csv(uploaded_history)
                    
                    # Usamos 'Numero' (Ticket) como llave única para saber si ya existe
                    if 'Numero' in df_history.columns and 'Numero' in df_full.columns:
                        # Convertir a string para asegurar comparación correcta
                        existing_tickets = df_history['Numero'].astype(str).unique()
                        current_tickets = df_full['Numero'].astype(str)
                        
                        # Filtro: Dejar solo los que NO están en existing_tickets
                        df_new_only = df_full[~current_tickets.isin(existing_tickets)]
                    else:
                        st.warning("El archivo histórico no contiene la columna 'Numero'. No se pudo filtrar.")
                except Exception as e:
                    st.error(f"Error leyendo el histórico: {e}")

            progress_bar.progress(100)
            status_text.success("✅ ¡Procesamiento completado!")

            # -----------------------------------------------------------------
            # RESULTADOS Y DESCARGAS
            # -----------------------------------------------------------------
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("1. Reporte Completo (Total)")
                st.write(f"Filas generadas: **{len(df_full)}**")
                st.dataframe(df_full.head(5))
                
                csv_full = io.BytesIO()
                df_full.to_csv(csv_full, index=False, encoding='utf-8-sig')
                st.download_button(
                    "📥 Descargar Todo",
                    data=csv_full.getvalue(),
                    file_name="Detalle_Pasajeros_Abandonos_FULL.csv",
                    mime="text/csv",
                    key="btn_full"
                )

            with col2:
                if uploaded_history is not None:
                    st.subheader("2. Solo Nuevos Registros")
                    if df_new_only is not None and not df_new_only.empty:
                        st.write(f"Nuevas filas encontradas: **{len(df_new_only)}**")
                        st.dataframe(df_new_only.head(5))
                        
                        csv_new = io.BytesIO()
                        df_new_only.to_csv(csv_new, index=False, encoding='utf-8-sig')
                        st.download_button(
                            "📥 Descargar Solo Nuevos",
                            data=csv_new.getvalue(),
                            file_name="Detalle_Pasajeros_Abandonos_NUEVOS.csv",
                            mime="text/csv",
                            key="btn_new"
                        )
                    elif df_new_only is not None and df_new_only.empty:
                        st.info("No se encontraron registros nuevos respecto al histórico subido.")
                else:
                    st.subheader("2. Solo Nuevos Registros")
                    st.info("Sube un archivo histórico en la barra lateral para habilitar esta opción.")

else:
    st.info("👋 Sube los archivos 'Master' y 'Reservas' para comenzar.")
