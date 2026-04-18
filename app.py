import streamlit as st
import dropbox
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore
import json
import pandas as pd

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor de Facturas IA", layout="wide")
st.title("📑 Extractor de Facturas con Gemini IA")

# --- BARRA LATERAL: CONFIGURACIÓN ---
with st.sidebar:
    st.header("Configuración de Llaves")
    gemini_key = st.text_input("Gemini API Key", type="password")
    dropbox_token = st.text_input("Dropbox Access Token", type="password")
    firebase_json = st.text_area("Contenido del JSON de Firebase (Pégalo aquí)")

# --- INICIALIZACIÓN DE SERVICIOS ---
if gemini_key and dropbox_token and firebase_json:
    # Configurar Gemini
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # Configurar Firebase (Evitar reinicialización)
    if not firebase_admin._apps:
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    # Configurar Dropbox
    dbx = dropbox.Dropbox(dropbox_token)

    # --- CUERPO PRINCIPAL ---
    tab1, tab2 = st.tabs(["Procesar Facturas", "Historial Guardado"])

    with tab1:
        st.subheader("Seleccionar Carpeta en Dropbox")
        ruta = st.text_input("Ruta de la carpeta (ej: /Contabilidad/2026/T1)", "/")
        
        if st.button("Buscar Facturas"):
            try:
                files = dbx.files_list_folder(ruta).entries
                pdf_files = [f for f in files if f.name.endswith('.pdf')]
                
                if not pdf_files:
                    st.warning("No se encontraron PDFs en esa ruta.")
                else:
                    st.write(f"Encontradas {len(pdf_files)} facturas.")
                    resultados = []

                    for file in pdf_files:
                        with st.spinner(f"Analizando {file.name}..."):
                            # Descargar de Dropbox
                            _, res = dbx.files_download(ruta + "/" + file.name)
                            pdf_content = res.content
                            
                            # Enviar a Gemini
                            prompt = "Extrae de esta factura: proveedor_cliente, num_factura, base_imponible, iva, total. Responde solo en formato JSON."
                            response = model.generate_content([prompt, {'mime_type': 'application/pdf', 'data': pdf_content}])
                            
                            # Limpiar y cargar JSON
                            clean_json = response.text.replace('```json', '').replace('```', '').strip()
                            resultados.append(json.loads(clean_json))

                    df = pd.DataFrame(resultados)
                    st.session_state['datos_actuales'] = resultados
                    st.table(df)

                    nombre_periodo = st.text_input("Nombre para guardar (ej: 1 Trimestre 2026)")
                    if st.button("Guardar en Firestore"):
                        db.collection("periodos").document(nombre_periodo).set({
                            "periodo": nombre_periodo,
                            "datos": resultados
                        })
                        st.success("¡Guardado correctamente!")
            except Exception as e:
                st.error(f"Error: {e}")

    with tab2:
        st.subheader("Consulta de periodos")
        docs = db.collection("periodos").stream()
        periodos = [doc.id for doc in docs]
        
        seleccion = st.selectbox("Elige un periodo guardado", ["Seleccione..."] + periodos)
        if seleccion != "Seleccione...":
            datos_guardados = db.collection("periodos").document(seleccion).get().to_dict()
            st.table(pd.DataFrame(datos_guardados['datos']))

else:
    st.info("Por favor, introduce todas las llaves en la barra lateral para comenzar.")
