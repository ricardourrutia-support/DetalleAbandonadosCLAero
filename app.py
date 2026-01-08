import pandas as pd
import numpy as np
import glob
import os
import sys

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Definición de rutas (puedes cambiarlas si mueves los archivos)
PATH_MASTER = "CL_Aeropuerto_Master_Compensaciones.xlsx"  # O .csv
PATH_RESERVAS = "Detalle Reservas_Full Data.csv"
FOLDER_TRANSACCIONES = "transacciones" # Carpeta donde pondrás los csv de transacciones
OUTPUT_FILE = "Reporte_Detalle_Pasajeros_Abandonos.csv"

# =============================================================================
# FUNCIONES AUXILIARES (ROBUSTEZ)
# =============================================================================

def read_robust_file(filepath):
    """
    Intenta leer un archivo data frame soportando .xlsx y .csv 
    con detección automática de separadores (',' o ';').
    """
    if not os.path.exists(filepath):
        print(f"❌ Error: No se encuentra el archivo: {filepath}")
        sys.exit(1)

    print(f"   Leyendo: {os.path.basename(filepath)}...")
    
    # Si es Excel
    if filepath.endswith('.xlsx') or filepath.endswith('.xls'):
        return pd.read_excel(filepath)
    
    # Si es CSV, probamos delimitadores
    try:
        # Intento 1: Coma
        df = pd.read_csv(filepath, sep=',')
        if len(df.columns) < 2: # Sospechoso, probamos punto y coma
            raise ValueError("Posible error de delimitador")
        return df
    except:
        try:
            # Intento 2: Punto y coma
            df = pd.read_csv(filepath, sep=';')
            return df
        except Exception as e:
            print(f"❌ Error crítico leyendo {filepath}: {e}")
            sys.exit(1)

def clean_id(x):
    """Normaliza los IDs para asegurar que el cruce (merge) funcione."""
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if s.endswith('.0'):
        return s[:-2]
    return s

def clean_and_parse_date_spanish(s):
    """
    Convierte fechas complejas tipo '16-12-2025, 12:00:00 a. m.' a datetime.
    Maneja abreviaciones en español y comas.
    """
    if pd.isna(s) or str(s).strip() == "":
        return pd.NaT
    
    s = str(s).strip().lower()
    # Limpieza de caracteres problemáticos
    s = s.replace(',', '')
    s = s.replace('.', '') # a.m. -> am
    s = s.replace('p m', 'pm').replace('a m', 'am')
    s = s.replace(' p m', 'pm').replace(' a m', 'am')
    
    # Mapeo simple de normalización por si quedan variantes
    s = s.replace('p.m.', 'pm').replace('a.m.', 'am')
    
    try:
        # Intentar formato día primero
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.NaT

# =============================================================================
# LÓGICA PRINCIPAL
# =============================================================================

def main():
    print("🚀 Iniciando generación del reporte 'Detalle Pasajeros Abandonos'...\n")

    # 1. CARGA DE DATOS
    # ---------------------------------------------------------
    print("1️⃣  Cargando archivos base...")
    df_master = read_robust_file(PATH_MASTER)
    df_reservas = read_robust_file(PATH_RESERVAS)

    print(f"2️⃣  Buscando transacciones en carpeta '{FOLDER_TRANSACCIONES}'...")
    all_trans_files = glob.glob(os.path.join(FOLDER_TRANSACCIONES, "*.csv"))
    
    if not all_trans_files:
        print(f"⚠️  ADVERTENCIA: No se encontraron archivos CSV en la carpeta '{FOLDER_TRANSACCIONES}'.")
        df_transacciones = pd.DataFrame(columns=['Id Reserva', 'Modo', 'F.Desde Aerop', 'F.Hacia Aerop'])
    else:
        print(f"   Se encontraron {len(all_trans_files)} archivos de transacciones. Unificando...")
        df_list = []
        for f in all_trans_files:
            try:
                # Usamos read_csv directo para transacciones (asumiendo formato consistente)
                # pero con manejo de errores por si acaso
                temp_df = pd.read_csv(f, sep=None, engine='python') 
                df_list.append(temp_df)
            except Exception as e:
                print(f"   ⚠️ Error leyendo {f}: {e}")
        
        if df_list:
            df_transacciones = pd.concat(df_list, ignore_index=True)
        else:
             df_transacciones = pd.DataFrame()

    # 2. PREPARACIÓN Y LIMPIEZA
    # ---------------------------------------------------------
    print("\n3️⃣  Limpiando datos y normalizando IDs...")
    
    # Estandarización de IDs
    # Ajusta nombres de columna según tus archivos reales
    # Master
    col_id_master = 'id_reserva'
    df_master['id_key'] = df_master[col_id_master].apply(clean_id)

    # Reservas (Journey)
    col_id_reservas = 'id_reservation_id'
    df_reservas['id_key'] = df_reservas[col_id_reservas].apply(clean_id)
    
    # Transacciones
    col_id_trans = 'Id Reserva'
    if col_id_trans in df_transacciones.columns:
        df_transacciones['id_key'] = df_transacciones[col_id_trans].apply(clean_id)
    else:
        df_transacciones['id_key'] = np.nan

    # Parseo de Fechas
    print("   Procesando fechas (esto puede tomar unos segundos)...")
    
    # Fecha en Reservas
    col_fecha_reserva = 'tm_start_local_at'
    df_reservas['tm_start_dt'] = pd.to_datetime(df_reservas[col_fecha_reserva], dayfirst=True, errors='coerce')

    # Fechas en Transacciones
    if not df_transacciones.empty:
        df_transacciones['F.Desde Aerop_dt'] = df_transacciones['F.Desde Aerop'].apply(clean_and_parse_date_spanish)
        df_transacciones['F.Hacia Aerop_dt'] = df_transacciones['F.Hacia Aerop'].apply(clean_and_parse_date_spanish)
    else:
        df_transacciones['F.Desde Aerop_dt'] = pd.NaT
        df_transacciones['F.Hacia Aerop_dt'] = pd.NaT
        df_transacciones['Modo'] = np.nan

    # 3. CRUCE DE INFORMACIÓN (JOINS)
    # ---------------------------------------------------------
    print("4️⃣  Cruzando bases de datos...")

    # Cruce 1: Master + Reservas
    merged = pd.merge(df_master, 
                      df_reservas[['id_key', 'tm_start_dt']], 
                      on='id_key', 
                      how='left')

    # Cruce 2: Resultado + Transacciones
    merged = pd.merge(merged, 
                      df_transacciones[['id_key', 'Modo', 'F.Desde Aerop_dt', 'F.Hacia Aerop_dt']], 
                      on='id_key', 
                      how='left')

    # 4. LÓGICA DE NEGOCIO (Date Calculation)
    # ---------------------------------------------------------
    print("5️⃣  Calculando 'Tm_start_local_at' real...")

    def get_final_tm(row):
        # 1. Prioridad: Base de Reservas (Journey)
        if pd.notna(row['tm_start_dt']):
            return row['tm_start_dt']
        
        # 2. Revisar Transacciones
        if pd.isna(row['Modo']):
            return pd.NaT # No encontrado en ninguna base
        
        # Caso RoundTrip o Conflicto
        if str(row['Modo']).strip() == 'Round':
            return "Ingresar Manualmente"
        
        has_desde = pd.notna(row['F.Desde Aerop_dt'])
        has_hacia = pd.notna(row['F.Hacia Aerop_dt'])
        
        if has_desde and has_hacia:
            return "Ingresar Manualmente"
        elif has_desde:
            return row['F.Desde Aerop_dt']
        elif has_hacia:
            return row['F.Hacia Aerop_dt']
        else:
            # Modo existe pero fechas vacías
            return pd.NaT

    merged['Calculated_Start'] = merged.apply(get_final_tm, axis=1)

    # 5. FORMATO FINAL
    # ---------------------------------------------------------
    print("6️⃣  Dando formato final al reporte...")

    # Extraer columnas Fecha y Hora
    def extract_date_str(val):
        if isinstance(val, str): return val 
        if pd.isna(val): return ""
        return val.strftime('%d/%m/%Y')

    def extract_hour_str(val):
        if isinstance(val, str) or pd.isna(val): return ""
        return int(val.hour)
    
    def format_full_datetime(val):
        if isinstance(val, str): return val
        if pd.isna(val): return ""
        return val.strftime('%d/%m/%Y %H:%M:%S')

    merged['Fecha'] = merged['Calculated_Start'].apply(extract_date_str)
    merged['Hora'] = merged['Calculated_Start'].apply(extract_hour_str)
    merged['Tm_start_local_at'] = merged['Calculated_Start'].apply(format_full_datetime)

    # Mapeo de columnas finales
    column_mapping = {
        'Fecha_x': 'Datetime Compensación', # Fecha original del master (usualmente se llama Fecha y al cruzar pd le pone _x)
        'Dirección de correo electrónico': 'Dirección de correo electrónico',
        'Numero': 'Numero',
        'Correo registrado en Cabify para realizar la carga': 'Correo registrado en Cabify para realizar la carga',
        'Total Compensación': 'Monto a compensar',
        'Motivo compensación': 'Motivo compensación',
        'id_reserva': 'id_reserva',
        'Clasificación': 'Compensación Aeropuerto',
        'Tm_start_local_at': 'Tm_start_local_at',
        'Fecha': 'Fecha', # Nuestra fecha calculada
        'Hora': 'Hora'
    }

    # Verificar si 'Fecha' del master sufrió rename por el merge
    if 'Fecha' in merged.columns and 'Fecha_x' not in merged.columns:
        column_mapping['Fecha'] = 'Datetime Compensación' # Si no hubo colisión de nombres
        # Pero cuidado, tenemos nuestra nueva columna 'Fecha' calculada. 
        # Pandas probablemente renombró la del Master a Fecha_x si creamos una nueva llamada Fecha.
        # Asumiremos que la del Master es la primera col.
    
    # Manejo seguro de columnas existentes
    final_cols = []
    for col_origin, col_dest in column_mapping.items():
        if col_origin in merged.columns:
            merged.rename(columns={col_origin: col_dest}, inplace=True)
            final_cols.append(col_dest)
        elif col_origin == 'Fecha_x' and 'Fecha_x' not in merged.columns and 'Fecha_y' in merged.columns:
             # Caso raro de colisión inversa
             merged.rename(columns={'Fecha_x': 'Datetime Compensación'}, inplace=True)

    # Filtrar solo las columnas deseadas que existan
    # Definimos el orden deseado
    desired_order = [
        'Datetime Compensación', 'Dirección de correo electrónico', 'Numero', 
        'Correo registrado en Cabify para realizar la carga', 'Monto a compensar', 
        'Motivo compensación', 'id_reserva', 'Compensación Aeropuerto', 
        'Tm_start_local_at', 'Fecha', 'Hora'
    ]
    
    # Seleccionamos solo las que logramos generar
    valid_cols = [c for c in desired_order if c in merged.columns]
    output_df = merged[valid_cols]

    # Guardar
    output_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig') # utf-8-sig para que Excel abra bien los tildes
    
    print(f"\n✅ ¡ÉXITO! Reporte generado: {OUTPUT_FILE}")
    print(f"   Filas procesadas: {len(output_df)}")

if __name__ == "__main__":
    main()
