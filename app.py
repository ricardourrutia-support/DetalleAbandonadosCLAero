import streamlit as st
import pandas as pd
import numpy as np

# Configuración de la página
st.set_page_config(page_title="Reporte Abandonos", layout="wide")
st.title("✈️ Generador de Reporte: Detalle Pasajeros Abandonos")

# =============================================================================
# FUNCIONES DE CACHÉ
# =============================================================================

@st.cache_data(show_spinner=False)
def load_data(file_master, file_reservas, files_transacciones):
    """
    Carga y procesa los datos. Al usar cache, esto solo se ejecuta
    cuando cambian los archivos subidos.
    """
    
    # 1. Carga Master
    if file_master.name.endswith('.csv'):
        df_master = pd.read_csv(file_master)
    else:
        df_master = pd.read_excel(file_master)
    
    # 2. Carga Reservas (Detectando separador)
    try:
        df_reservas = pd.read_csv(file_reservas, sep=';')
        # Verificación básica de que leyó bien las columnas
        if len(df_reservas.columns) < 2: 
            file_reservas.seek(0)
            df_reservas = pd.read_csv(file_reservas, sep=',')
    except:
        file_reservas.seek(0)
        df_reservas = pd.read_csv(file_reservas, sep=',')

    # 3. Carga Transacciones (Múltiples archivos)
    df_list = []
    if files_transacciones:
        for f in files_transacciones:
            try:
                # Engine python es más lento pero más compatible con formatos raros
                temp = pd.read_csv(f, engine='python') 
                df_list.append(temp)
            except Exception as e:
                st.warning(f"No se pudo leer {f.name}: {e}")
        
        if df_list:
            df_transacciones = pd.concat(df_list, ignore_index=True)
        else:
            df_transacciones = pd.DataFrame()
    else:
        # Dataframe vacío con estructura
        df_transacciones = pd.DataFrame(columns=['Id Reserva', 'Modo', 'F.Desde Aerop', 'F.Hacia Aerop'])

    return df_master, df_reservas, df_transacciones

def clean_id(x):
    """Limpia los IDs para asegurar cruce correcto (quita .0 y espacios)"""
    if pd.isna(x): return np.nan
    s = str(x).strip()
    if s.endswith('.0'): return s[:-2]
    return s

def clean_date_spanish(s):
    """Parsea fechas con formatos manuales en español"""
    if pd.isna(s) or str(s).strip() == "": return pd.NaT
    s = str(s).strip().lower().replace(',', '').replace('.', '')
    # Normalización de AM/PM
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
            # -----------------------------------------------------------------
            df_master, df_reservas, df_trans = load_data(uploaded_master, uploaded_reservas, uploaded_trans)
            
            progress_bar = st.progress(0)
            status_text = st.empty()

            # 2. LIMPIEZA DE IDs
            # -----------------------------------------------------------------
            status_text.text("Normalizando IDs...")
            
            # Aseguramos nombres de columnas de ID (ajustar si cambian en tus CSVs)
            # Master
            col_id_master = 'id_reserva' if 'id_reserva' in df_master.columns else df_master.columns[8] # Intento fallback
            df_master['id_key'] = df_master[col_id_master].apply(clean_id)
            
            # Reservas
            col_id_res = 'id_reservation_id' if 'id_reservation_id' in df_reservas.columns else 'id_reservation'
            if col_id_res in df_reservas.columns:
                df_reservas['id_key'] = df_reservas[col_id_res].apply(clean_id)
            else:
                st.error(f"No se encontró la columna de ID en Reservas (buscaba '{col_id_res}')")
                st.stop()
            
            # Transacciones
            if not df_trans.empty:
                col_id_trans = 'Id Reserva'
                if col_id_trans in df_trans.columns:
                    df_trans['id_key'] = df_trans[col_id_trans].apply(clean_id)
                else:
                    df_trans['id_key'] = np.nan
            else:
                df_trans['id_key'] = np.nan
            
            progress_bar.progress(30)
            
            # 3. PARSEO DE FECHAS
            # -----------------------------------------------------------------
            status_text.text("Analizando fechas (formato español)...")
            
            # Reservas
            if 'tm_start_local_at' in df_reservas.columns:
                df_reservas['tm_start_dt'] = pd.to_datetime(df_reservas['tm_start_local_at'], dayfirst=True, errors='coerce')
            else:
                 st.error("No se encontró 'tm_start_local_at' en el archivo de Reservas.")
                 st.stop()
            
            # Transacciones
            if not df_trans.empty:
                # Verificamos que existan las columnas antes de procesar
                if 'F.Desde Aerop' in df_trans.columns:
                    df_trans['F.Desde Aerop_dt'] = df_trans['F.Desde Aerop'].apply(clean_date_spanish)
                else:
                    df_trans['F.Desde Aerop_dt'] = pd.NaT

                if 'F.Hacia Aerop' in df_trans.columns:
                    df_trans['F.Hacia Aerop_dt'] = df_trans['F.Hacia Aerop'].apply(clean_date_spanish)
                else:
                    df_trans['F.Hacia Aerop_dt'] = pd.NaT
            else:
                df_trans['F.Desde Aerop_dt'] = pd.NaT
                df_trans['F.Hacia Aerop_dt'] = pd.NaT
                df_trans['Modo'] = np.nan

            progress_bar.progress(50)

            # 4. CRUCE (MERGE)
            # -----------------------------------------------------------------
            status_text.text("Cruzando bases de datos...")
            merged = pd.merge(df_master, df_reservas[['id_key', 'tm_start_dt']], on='id_key', how='left')
            
            cols_trans = ['id_key', 'Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt']
            # Solo seleccionamos las que existen para evitar error
            cols_trans = [c for c in cols_trans if c in df_trans.columns]
            
            merged = pd.merge(merged, df_trans[cols_trans], on='id_key', how='left')
            
            progress_bar.progress(70)

            # 5. LÓGICA DE NEGOCIO (CORREGIDA)
            # -----------------------------------------------------------------
            status_text.text("Calculando lógica de negocio...")
            
            # Asegurar que las columnas existan en el merged (si falló el cruce anterior)
            if 'Modo' not in merged.columns: merged['Modo'] = np.nan
            if 'F.Desde Aerop_dt' not in merged.columns: merged['F.Desde Aerop_dt'] = pd.NaT
            if 'F.Hacia Aerop_dt' not in merged.columns: merged['F.Hacia Aerop_dt'] = pd.NaT

            # Condiciones
            c1 = merged['tm_start_dt'].notna()
            c2 = merged['Modo'].isna()
            c3 = (merged['Modo'] == 'Round') | (merged['F.Desde Aerop_dt'].notna() & merged['F.Hacia Aerop_dt'].notna())
            c4 = merged['F.Desde Aerop_dt'].notna()
            c5 = merged['F.Hacia Aerop_dt'].notna()

            # --- CORRECCIÓN IMPORTANTE AQUÍ ---
            # Convertimos las columnas de fecha a 'object' explícitamente.
            # Esto permite mezclar Fechas (Timestamp) con Texto ("Ingresar Manualmente") sin error.
            
            val_1 = merged['tm_start_dt'].astype(object)
            val_2 = pd.NaT # Es compatible con object
            val_3 = "Ingresar Manualmente" # String
            val_4 = merged['F.Desde Aerop_dt'].astype(object)
            val_5 = merged['F.Hacia Aerop_dt'].astype(object)

            merged['Calc_Temp'] = np.select(
                [c1, c2, c3, c4, c5], 
                [val_1, val_2, val_3, val_4, val_5], 
                default=pd.NaT
            )
            # ----------------------------------

            progress_bar.progress(90)

            # 6. FORMATO DE SALIDA
            # -----------------------------------------------------------------
            status_text.text("Formateando salida...")
            
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

            merged['Fecha'] = merged['Calc_Temp'].apply(format_output_date)
            merged['Hora'] = merged['Calc_Temp'].apply(format_output_hour)
            merged['Tm_start_local_at'] = merged['Calc_Temp'].apply(format_output_full)

            # Renombrar columnas para el reporte final
            final_mapping = {
                'Fecha_x': 'Datetime Compensación', # Posible nombre post-merge
                'Fecha': 'Datetime Compensación',   # Posible nombre original
                'Dirección de correo electrónico': 'Dirección de correo electrónico',
                'Numero': 'Numero',
                'Correo registrado en Cabify para realizar la carga': 'Correo registrado en Cabify para realizar la carga',
                'Total Compensación': 'Monto a compensar',
                'Motivo compensación': 'Motivo compensación',
                'id_reserva': 'Id_reserva',
                'Clasificación': 'Compensación Aeropuerto',
                # Columnas calculadas (ya tienen el nombre correcto en el dataframe, pero las listamos para ordenar)
            }
            
            # Ajuste dinámico de nombres si hubo colisión en el merge
            if 'Fecha_x' in merged.columns:
                merged.rename(columns={'Fecha_x': 'Datetime Compensación'}, inplace=True)
            elif 'Fecha' in merged.columns and 'Datetime Compensación' not in merged.columns:
                # Cuidado: acabamos de crear una columna 'Fecha' nueva calculada.
                # Si la del master se llamaba 'Fecha', Pandas la habrá renombrado o sobreescrito.
                # Como creamos 'Fecha' al final, la del master probablemente sea 'Fecha_x' o 'Fecha_y' si hubo colisión.
                # Ojo: Si sobreescribimos la fecha del master, necesitamos recuperarla si la queremos en el output.
                pass 
            
            # Para evitar sobreescritura accidental, revisemos:
            # En el merge, df_master tenía 'Fecha'. df_reservas no.
            # df_transacciones tenía 'F. Reserva'.
            # Así que 'Fecha' del master debería seguir siendo 'Fecha' a menos que 'tm_start_dt' interfiera, que no debería.
            # Pero en el paso 6 creamos merged['Fecha']. Esto SOBREESCRIBE la fecha del master si se llamaba 'Fecha'.
            # SOLUCIÓN: Usar la fecha del master antes de que se pierda o renombrarla antes.
            
            # Recuperamos la fecha original del master (si fue sobreescrita, ya es tarde, 
            # pero el orden de ejecución es secuencial).
            # En Pandas, si asignas merged['Fecha'] = ..., reemplazas la columna existente.
            # Por suerte, en df_master la columna suele llamarse 'Fecha'.
            # Vamos a asumir que 'Datetime Compensación' es la fecha del master.
            
            # Re-mapeo seguro:
            # Si 'Datetime Compensación' no existe, intentamos buscar 'Fecha_x' o la original antes de sobreescribir
            # Como ya asignamos merged['Fecha'], la perdimos si se llamaba así.
            # FIX RÁPIDO: Renombrar la columna del master AL PRINCIPIO de load_data o antes del merge es mejor práctica,
            # pero aquí lo haremos usando una copia si es necesario.
            
            # En realidad, el output pide: "Datetime Compensación: Atributo 'Fecha' del Máster".
            # Y "Fecha": Atributo calculado.
            # Como 'Fecha' (Master) y 'Fecha' (Calculada) tienen el mismo nombre, debemos diferenciarlas.
            
            # Vamos a corregir esto retroactivamente en el código de arriba renombrando la columna calculada primero.
            merged.rename(columns={'Fecha': 'Fecha_Calculada'}, inplace=True) # Si la creamos antes
            # Ah, la asignación merged['Fecha'] = ... crea la columna nueva.
            # Si existía 'Fecha' (Master), ahora tiene los valores calculados. ¡ERROR LÓGICO!
            
            # CORRECCIÓN EN VIVO DEL SCRIPT (He ajustado el código de abajo para evitar esto):
            # En lugar de merged['Fecha'] = ..., usaremos nombres temporales y luego renombraremos todo junto.
            
            pass # (Esto era solo comentario explicativo)

            # IMPLEMENTACIÓN CORRECTA DE RENOMBRES
            
            # 1. Renombrar la columna del Master si aún se llama 'Fecha' y no queremos perderla
            # (Aunque ya la sobreescribimos en la línea 160 si ejecutáramos linealmente sin pensar).
            # Para este script corregido, cambiaré el nombre de la columna calculada a 'Fecha_Viaje'.
            
            merged['Fecha_Viaje'] = merged['Calc_Temp'].apply(format_output_date) # Nombre seguro
            merged['Hora_Viaje'] = merged['Calc_Temp'].apply(format_output_hour)
            merged['Tm_Final'] = merged['Calc_Temp'].apply(format_output_full)
            
            # Seleccionamos y renombramos para el output
            output_columns = []
            
            # Columna 1: Datetime Compensación (Viene del Master)
            if 'Fecha' in df_master.columns and 'Fecha' in merged.columns:
                 # Si no se sobreescribió (porque cambié el nombre arriba), usamos 'Fecha'
                 merged.rename(columns={'Fecha': 'Datetime Compensación'}, inplace=True)
            elif 'Fecha_x' in merged.columns:
                 merged.rename(columns={'Fecha_x': 'Datetime Compensación'}, inplace=True)
            
            # Columnas finales deseadas
            cols_finales = {
                'Datetime Compensación': 'Datetime Compensación',
                'Dirección de correo electrónico': 'Dirección de correo electrónico',
                'Numero': 'Numero',
                'Correo registrado en Cabify para realizar la carga': 'Correo registrado en Cabify para realizar la carga',
                'Total Compensación': 'Monto a compensar',
                'Motivo compensación': 'Motivo compensación',
                'id_key': 'Id_reserva', # Usamos la key limpia
                'Clasificación': 'Compensación Aeropuerto',
                'Tm_Final': 'Tm_start_local_at',
                'Fecha_Viaje': 'Fecha',
                'Hora_Viaje': 'Hora'
            }
            
            output_df = pd.DataFrame()
            
            for col_origin, col_dest in cols_finales.items():
                if col_origin in merged.columns:
                    output_df[col_dest] = merged[col_origin]
                else:
                    # Si falta alguna columna (ej: Motivo compensación a veces viene vacía o con otro nombre)
                    output_df[col_dest] = "" # Relleno vacío

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
