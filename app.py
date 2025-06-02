import pandas as pd
import streamlit as st
from streamlit.connections import ExperimentalBaseConnection
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
import gspread
from google.oauth2 import service_account

# Configuración de la página
st.set_page_config(
    page_title="Análisis Pedidos vs Facturas",
    layout="wide",
    initial_sidebar_state="expanded"
)

class GSheetsConnection(ExperimentalBaseConnection):
    def _connect(self, **kwargs):
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return gspread.authorize(credentials)

    def get_data(self, spreadsheet_url: str, worksheet_name: str = None, **kwargs) -> pd.DataFrame:
        conn = self._connect()
        sheet = conn.open_by_url(spreadsheet_url)
        
        if worksheet_name:
            worksheet = sheet.worksheet(worksheet_name)
        else:
            worksheet = sheet.get_worksheet(0)
        
        return pd.DataFrame(worksheet.get_all_records())

@st.cache_data(ttl=600)
def load_data():
    try:
        # Configuración de credenciales
        gcp_service_account = {
            "type": st.secrets["gcp_service_account"]["type"],
            "project_id": st.secrets["gcp_service_account"]["project_id"],
            "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
            "private_key": st.secrets["gcp_service_account"]["private_key"],
            "client_email": st.secrets["gcp_service_account"]["client_email"],
            "client_id": st.secrets["gcp_service_account"]["client_id"],
            "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
            "token_uri": st.secrets["gcp_service_account"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"]
        }
        
        # Crear conexión
        conn = GSheetsConnection("gsheets")
        
        # Cargar datos
        pedidos = conn.get_data(
            st.secrets["connections.gsheets"]["spreadsheet_url_pedidos"],
            st.secrets["connections.gsheets"]["worksheet_name"]
        )
        
        facturas = conn.get_data(
            st.secrets["connections.gsheets"]["spreadsheet_url_facturas"],
            st.secrets["connections.gsheets"]["worksheet_name"]
        )
        
        # Procesamiento de datos
        pedidos['Fecha_Pedido'] = pd.to_datetime(pedidos['Fecha_Pedido'])
        facturas['Fecha_Factura'] = pd.to_datetime(facturas['Fecha_Factura'])
        
        # Resto del procesamiento (igual que en tu código original)
        # ...
        
        return pedidos, facturas, merged
    
    except Exception as e:
        st.error(f"Error al cargar datos: {str(e)}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# [El resto de tus funciones (vista_resumen_general, vista_analisis_cliente, etc.) permanecen igual]

def main():
    st.title("📊 Dashboard de Pedidos vs Facturas")
    
    # Cargar datos
    pedidos, facturas, merged = load_data()
    
    if merged.empty:
        st.error("No se pudieron cargar los datos. Verifica la configuración.")
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
