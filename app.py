import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Configuración de la página
st.set_page_config(
    page_title="Análisis Pedidos vs Facturas",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuración para acceder a Google Sheets
def setup_gsheets():
    # Crear credenciales (necesitarás un archivo JSON de credenciales de servicio de Google)
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    # Aquí debes colocar tu archivo JSON de credenciales o configurar las credenciales de otra manera
    creds = ServiceAccountCredentials.from_json_keyfile_name('tu_credencial.json', scope)
    client = gspread.authorize(creds)
    return client

# URLs de los archivos
PEDIDOS_URL = "https://docs.google.com/spreadsheets/d/1j49k__OxEMGFLX3dIU2afhg0WWWDBjl7/edit#gid=0"
FACTURAS_URL = "https://docs.google.com/spreadsheets/d/1S6n4QI2VH6rBvz5BvPaEFzJRBJCDLNK1/edit#gid=0"

def get_sheet_data(url, sheet_name=None):
    """Obtiene datos de una hoja de Google Sheets"""
    try:
        client = setup_gsheets()
        sheet = client.open_by_url(url)
        
        if sheet_name:
            worksheet = sheet.worksheet(sheet_name)
        else:
            worksheet = sheet.get_worksheet(0)  # Primera hoja por defecto
            
        records = worksheet.get_all_records()
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Error al cargar datos desde Google Sheets: {str(e)}")
        return pd.DataFrame()

def parse_hora(hora_str):
    """Convierte diferentes formatos de hora a hora numérica"""
    if pd.isna(hora_str):
        return np.nan
    
    hora_str = str(hora_str).strip()
    
    if ':' in hora_str:
        try:
            return int(hora_str.split(':')[0])
        except:
            return np.nan
    
    try:
        return int(float(hora_str))
    except:
        return np.nan

def determinar_fecha_factura(fecha_pedido):
    """Determina la fecha esperada de factura según reglas de negocio"""
    if fecha_pedido.weekday() == 5:  # Sábado
        return fecha_pedido + timedelta(days=2)
    else:
        return fecha_pedido + timedelta(days=1)

@st.cache_data
def load_data():
    try:
        # Cargar archivos desde Google Sheets
        pedidos = get_sheet_data(PEDIDOS_URL)
        facturas = get_sheet_data(FACTURAS_URL)
        
        if pedidos.empty or facturas.empty:
            st.error("No se pudieron cargar los datos. Verifica las URLs y los permisos.")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        # Convertir tipos de datos
        pedidos['Fecha_Pedido'] = pd.to_datetime(pedidos['Fecha_Pedido'])
        facturas['Fecha_Factura'] = pd.to_datetime(facturas['Fecha_Factura'])
        
        # Procesamiento de horas
        pedidos['Hora_Pedido'] = pedidos['Hora_Pedido'].apply(parse_hora)
        pedidos = pedidos.dropna(subset=['Hora_Pedido'])
        pedidos['Hora_Pedido'] = pedidos['Hora_Pedido'].astype(int)
        
        # Columnas adicionales
        pedidos['Dia_Semana'] = pedidos['Fecha_Pedido'].dt.day_name(locale='es')
        pedidos['Semana'] = pedidos['Fecha_Pedido'].dt.isocalendar().week
        pedidos['Mes'] = pedidos['Fecha_Pedido'].dt.month
        pedidos['Fecha_Factura_Esperada'] = pedidos['Fecha_Pedido'].apply(determinar_fecha_factura)
        
        # Merge considerando fecha esperada de factura
        merged = pd.merge(
            pedidos,
            facturas,
            how='left',
            left_on=['ID_Cliente', 'Vendedor', 'ID_Producto', 'Fecha_Factura_Esperada'],
            right_on=['ID_Cliente', 'Vendedor', 'ID_Producto', 'Fecha_Factura'],
            suffixes=('_Pedido', '_Factura')
        )
        
        # Asegurar que tenemos una columna Cliente válida
        if 'Cliente_Pedido' in merged.columns:
            merged['Cliente'] = merged['Cliente_Pedido']
        elif 'Cliente_Factura' in merged.columns:
            merged['Cliente'] = merged['Cliente_Factura'].fillna(merged['Cliente_Pedido'])
        elif 'Cliente' in merged.columns:
            pass  # Ya existe la columna Cliente
        else:
            st.error("No se encontró ninguna columna de cliente válida")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        # Verificar columnas después del merge
        if 'Producto_Pedido' in merged.columns:
            merged['Producto'] = merged['Producto_Pedido']
        
        # Cálculo de métricas basadas en CAJA (monto)
        merged['Diferencia_Caja'] = merged['Monto_Pedido'] - merged['Monto_Factura'].fillna(0)
        merged['%_Cumplimiento_Caja'] = np.where(
            merged['Monto_Pedido'] > 0,
            (merged['Monto_Factura'].fillna(0) / merged['Monto_Pedido']) * 100,
            0
        )
        
        # Clasificar cumplimiento basado en caja
        merged['Cumplimiento_Categoria_Caja'] = pd.cut(
            merged['%_Cumplimiento_Caja'],
            bins=[-1, 0, 50, 80, 95, 100],
            labels=['Nada', 'Bajo', 'Medio', 'Alto', 'Completo']
        )
        
        return pedidos, facturas, merged
    
    except Exception as e:
        st.error(f"Error procesando datos: {str(e)}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# [El resto de las funciones (vista_resumen_general, vista_analisis_cliente, etc.) permanecen iguales que en el código anterior]

def main():
    st.title("📊 Dashboard de Pedidos vs Facturas (Caja)")
    
    # Cargar datos
    pedidos, facturas, merged = load_data()
    
    if merged.empty:
        st.error("No se pudieron cargar los datos. Verifica las conexiones y los permisos.")
        st.stop()
    
    # Mostrar columnas disponibles para depuración
    st.sidebar.write("Columnas disponibles:", merged.columns.tolist())
    
    # Filtros principales
    st.sidebar.header("🔍 Filtros")
    
    # Fechas
    fecha_min = merged['Fecha_Pedido'].min().date()
    fecha_max = merged['Fecha_Pedido'].max().date()
    
    fecha_inicio = st.sidebar.date_input(
        "Fecha inicio",
        fecha_max - timedelta(days=30),
        min_value=fecha_min,
        max_value=fecha_max
    )
    fecha_fin = st.sidebar.date_input(
        "Fecha fin", 
        fecha_max,
        min_value=fecha_min,
        max_value=fecha_max
    )
    
    # Filtros adicionales
    regiones = st.sidebar.multiselect(
        "Regiones",
        options=merged['Region'].unique(),
        default=merged['Region'].unique()
    )
    
    vendedores = st.sidebar.multiselect(
        "Vendedores",
        options=merged['Vendedor'].unique(),
        default=merged['Vendedor'].unique()
    )
    
    # Aplicar filtros
    filtered = merged[
        (merged['Fecha_Pedido'].dt.date >= fecha_inicio) &
        (merged['Fecha_Pedido'].dt.date <= fecha_fin)
    ]
    
    if regiones:
        filtered = filtered[filtered['Region'].isin(regiones)]
    if vendedores:
        filtered = filtered[filtered['Vendedor'].isin(vendedores)]
    
    # Pestañas principales
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🏠 Resumen General", 
        "👥 Por Cliente", 
        "📦 Por Producto", 
        "👤 Por Vendedor",
        "🔍 Detalle Completo"
    ])
    
    with tab1:
        vista_resumen_general(filtered)
    
    with tab2:
        vista_analisis_cliente(filtered)
    
    with tab3:
        vista_analisis_producto(filtered)
    
    with tab4:
        vista_analisis_vendedor(filtered)
    
    with tab5:
        vista_detalle_completo(filtered)

if __name__ == "__main__":
    main()