import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
import requests
from io import StringIO

# Configuración de la página
st.set_page_config(
    page_title="Análisis Pedidos vs Facturas",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URLs públicas de tus Google Sheets (formato de exportación CSV)
PEDIDOS_URL = "https://docs.google.com/spreadsheets/d/1j49k__OxEMGFLX3dIU2afhg0WWWDBjl7/export?format=csv"
FACTURAS_URL = "https://docs.google.com/spreadsheets/d/1S6n4QI2VH6rBvz5BvPaEFzJRBJCDLNK1/export?format=csv"

def load_sheet_data(url):
    """Carga datos desde una hoja pública de Google Sheets"""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Verifica errores HTTP
        return pd.read_csv(StringIO(response.text))
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

@st.cache_data(ttl=600)  # Cache de 10 minutos
def load_data():
    try:
        # Cargar archivos desde Google Sheets
        pedidos = load_sheet_data(PEDIDOS_URL)
        facturas = load_sheet_data(FACTURAS_URL)
        
        if pedidos.empty or facturas.empty:
            st.error("No se pudieron cargar los datos. Verifica que las hojas sean públicas.")
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

def vista_resumen_general(filtered):
    """Vista de resumen general basado en CAJA (monto)"""
    st.header("📊 Resumen General (Caja)")
    
    # KPIs principales basados en monto (caja)
    total_pedido = filtered['Monto_Pedido'].sum()
    total_facturado = filtered['Monto_Factura'].sum()
    diferencia = total_pedido - total_facturado
    cumplimiento = (total_facturado / total_pedido * 100) if total_pedido > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Pedido", f"${total_pedido:,.2f}")
    col2.metric("Total Facturado", f"${total_facturado:,.2f}")
    col3.metric("Diferencia", f"${diferencia:,.2f}")
    col4.metric("% Cumplimiento", f"{cumplimiento:.1f}%")
    
    # Gráfico de tendencia diaria basado en monto
    st.subheader("📅 Tendencia Diaria (Caja)")
    diario = filtered.groupby(filtered['Fecha_Pedido'].dt.date).agg({
        'Monto_Pedido': 'sum',
        'Monto_Factura': 'sum',
        'Diferencia_Caja': 'sum'
    }).reset_index()
    
    fig = px.line(
        diario,
        x='Fecha_Pedido',
        y=['Monto_Pedido', 'Monto_Factura'],
        labels={'value': 'Monto ($)', 'variable': 'Tipo'},
        title="Pedido vs Facturado por Día (Caja)"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Impacto por día de semana basado en monto
    st.subheader("📆 Impacto por Día de la Semana (Caja)")
    dia_semana = filtered.groupby('Dia_Semana').agg({
        'Monto_Pedido': 'sum',
        'Monto_Factura': 'sum',
        'Diferencia_Caja': 'sum'
    }).reset_index()
    
    fig = px.bar(
        dia_semana,
        x='Dia_Semana',
        y='Diferencia_Caja',
        title="Monto No Facturado por Día de la Semana (Caja)",
        color='Dia_Semana'
    )
    st.plotly_chart(fig, use_container_width=True)

def vista_analisis_cliente(filtered):
    """Vista de análisis por cliente con selección múltiple"""
    st.header("👥 Análisis por Cliente (Caja)")
    
    # Verificar si existe la columna Cliente
    if 'Cliente' not in filtered.columns:
        st.error("Error: No se encontró la columna 'Cliente' en los datos")
        st.write("Columnas disponibles:", filtered.columns.tolist())
        return
    
    # Selección múltiple de clientes
    clientes_seleccionados = st.multiselect(
        "Seleccionar Cliente(s)",
        options=sorted(filtered['Cliente'].unique()),
        default=[sorted(filtered['Cliente'].unique())[0]] if len(filtered['Cliente'].unique()) > 0 else []
    )
    
    if not clientes_seleccionados:
        st.warning("Por favor seleccione al menos un cliente")
        return
    
    cliente_data = filtered[filtered['Cliente'].isin(clientes_seleccionados)]
    
    if cliente_data.empty:
        st.warning("No hay datos para estos clientes en el período seleccionado")
        return
    
    # Métricas clave basadas en caja
    cumplimiento = cliente_data['Monto_Factura'].sum() / cliente_data['Monto_Pedido'].sum() * 100
    monto_perdido = cliente_data['Diferencia_Caja'].sum()
    pedidos_totales = cliente_data['ID_Pedido'].nunique()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Cumplimiento", f"{cumplimiento:.1f}%")
    col2.metric("Monto No Facturado", f"${monto_perdido:,.2f}")
    col3.metric("Total Pedidos", pedidos_totales)
    
    # Evolución semanal basada en caja
    st.subheader("📈 Evolución Semanal (Caja)")
    evolucion = cliente_data.groupby(['Semana', 'Cliente']).agg({
        'Monto_Pedido': 'sum',
        'Monto_Factura': 'sum',
        'Diferencia_Caja': 'sum'
    }).reset_index()
    
    fig = px.line(
        evolucion,
        x='Semana',
        y=['Monto_Pedido', 'Monto_Factura'],
        color='Cliente',
        title=f"Pedido vs Facturado por Semana (Caja)"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Tabla resumen por cliente
    st.subheader("📋 Resumen por Cliente")
    resumen_cliente = cliente_data.groupby('Cliente').agg({
        'Monto_Pedido': 'sum',
        'Monto_Factura': 'sum',
        'Diferencia_Caja': 'sum',
        '%_Cumplimiento_Caja': 'mean',
        'ID_Pedido': 'nunique'
    }).reset_index()
    
    st.dataframe(
        resumen_cliente.sort_values('Diferencia_Caja', ascending=False),
        height=500,
        use_container_width=True
    )

def vista_analisis_producto(filtered):
    """Vista de análisis por producto con selección de cantidad"""
    st.header("📦 Análisis por Producto (Caja)")
    
    # Configurar número de productos a mostrar
    col1, col2 = st.columns(2)
    with col1:
        num_productos_top = st.number_input(
            "Número de productos a mostrar en TOP",
            min_value=1,
            max_value=50,
            value=10
        )
    with col2:
        num_productos_bottom = st.number_input(
            "Número de productos a mostrar en BOTTOM",
            min_value=1,
            max_value=50,
            value=10
        )
    
    # Top productos con mayor diferencia en caja
    producto_analysis = filtered.groupby(['ID_Producto', 'Producto']).agg({
        'Monto_Pedido': 'sum',
        'Monto_Factura': 'sum',
        'Diferencia_Caja': 'sum',
        'ID_Pedido': 'count'
    }).reset_index()
    
    producto_analysis['% Cumplimiento'] = (producto_analysis['Monto_Factura'] / producto_analysis['Monto_Pedido'] * 100).round(1)
    
    st.subheader(f"🔝 Top {num_productos_top} Productos con Mayor Diferencia (Caja)")
    st.dataframe(
        producto_analysis.sort_values('Diferencia_Caja', ascending=False).head(num_productos_top),
        height=500,
        use_container_width=True
    )
    
    st.subheader(f"🔚 Bottom {num_productos_bottom} Productos con Menor Diferencia (Caja)")
    st.dataframe(
        producto_analysis.sort_values('Diferencia_Caja', ascending=True).head(num_productos_bottom),
        height=500,
        use_container_width=True
    )
    
    # Análisis por categoría de cumplimiento basado en caja
    st.subheader("📊 Distribución por Nivel de Cumplimiento (Caja)")
    cumplimiento_cat = filtered.groupby('Cumplimiento_Categoria_Caja').agg({
        'ID_Pedido': 'count',
        'Diferencia_Caja': 'sum'
    }).reset_index()
    
    fig = px.pie(
        cumplimiento_cat,
        names='Cumplimiento_Categoria_Caja',
        values='Diferencia_Caja',
        title="Distribución del Monto No Facturado por Nivel de Cumplimiento"
    )
    st.plotly_chart(fig, use_container_width=True)

def vista_analisis_vendedor(filtered):
    """Vista de análisis por vendedor con métricas mejoradas"""
    st.header("👤 Análisis por Vendedor (Caja)")
    
    # Desempeño por vendedor basado en caja
    vendedor_analysis = filtered.groupby('Vendedor').agg({
        'Monto_Pedido': 'sum',
        'Monto_Factura': 'sum',
        'Diferencia_Caja': 'sum',
        'ID_Pedido': 'count',
        'Cumplimiento_Categoria_Caja': lambda x: (x == 'Completo').mean() * 100
    }).reset_index()
    
    vendedor_analysis['% Cumplimiento'] = (vendedor_analysis['Monto_Factura'] / vendedor_analysis['Monto_Pedido'] * 100).round(1)
    vendedor_analysis['% Pedidos Completos'] = vendedor_analysis['Cumplimiento_Categoria_Caja'].round(1)
    
    # Calcular pedidos con diferencia
    pedidos_con_diferencia = filtered[filtered['Diferencia_Caja'] > 0].groupby('Vendedor')['ID_Pedido'].nunique().reset_index()
    pedidos_con_diferencia.rename(columns={'ID_Pedido': 'Pedidos_con_Diferencia'}, inplace=True)
    
    vendedor_analysis = pd.merge(
        vendedor_analysis,
        pedidos_con_diferencia,
        on='Vendedor',
        how='left'
    ).fillna(0)
    
    vendedor_analysis['% Pedidos con Diferencia'] = (vendedor_analysis['Pedidos_con_Diferencia'] / vendedor_analysis['ID_Pedido'] * 100).round(1)
    
    st.subheader("Desempeño por Vendedor (Caja)")
    st.dataframe(
        vendedor_analysis.sort_values('% Cumplimiento', ascending=True),
        height=500,
        use_container_width=True
    )
    
    # Gráfico de cumplimiento por vendedor
    st.subheader("📊 Cumplimiento por Vendedor (Caja)")
    fig = px.bar(
        vendedor_analysis.sort_values('% Cumplimiento', ascending=True),
        x='% Cumplimiento',
        y='Vendedor',
        orientation='h',
        title="Porcentaje de Cumplimiento por Vendedor (Caja)"
    )
    st.plotly_chart(fig, use_container_width=True)

def vista_detalle_completo(filtered):
    """Vista de detalle completo basado en caja"""
    st.header("🔍 Detalle Completo (Caja)")
    
    # Filtros adicionales
    col1, col2 = st.columns(2)
    with col1:
        cumplimiento_min = st.slider("Cumplimiento mínimo (%)", 0, 100, 0)
    with col2:
        diferencia_min = st.number_input("Diferencia mínima en monto ($)", min_value=0, value=0)
    
    # Aplicar filtros adicionales
    filtered_view = filtered[
        (filtered['%_Cumplimiento_Caja'] >= cumplimiento_min) &
        (filtered['Diferencia_Caja'].abs() >= diferencia_min)
    ]
    
    st.dataframe(
        filtered_view.sort_values('Diferencia_Caja', ascending=False),
        height=600,
        use_container_width=True
    )

def main():
    st.title("📊 Dashboard de Pedidos vs Facturas (Caja)")
    
    # Cargar datos
    pedidos, facturas, merged = load_data()
    
    if merged.empty:
        st.error("No se pudieron cargar los datos. Verifica que las hojas sean públicas y las URLs correctas.")
        st.stop()
    
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
