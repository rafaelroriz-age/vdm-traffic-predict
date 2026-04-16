# VMD Goiás - Estimativa de Volume Médio Diário de Tráfego

Sistema de estimativa de Volume Médio Diário (VMD) para a malha rodoviária estadual de Goiás, utilizando Machine Learning e Network Analysis.

## Funcionalidades

- **ML Pipeline**: Random Forest, XGBoost, SOM (Self-Organizing Maps), IDW (Inverse Distance Weighting), Ensemble
- **Network Analysis**: Grafo rodoviário com centralidade (degree, betweenness, closeness) via NetworkX
- **Mapa Interativo**: Leaflet com segmentos coloridos por VMD, popups detalhados, filtros
- **Validação Espacial**: K-Fold CV agrupado por regional para evitar data leakage espacial

## Resultados

- **2.050 segmentos** mapeados (562 observados, 1.488 estimados)
- **Melhor modelo**: Random Forest (R²=0.407, RMSE=2.035)
- **Top feature**: `neighbor_mean_vmd` (importância 0.52) - VMD médio dos vizinhos na rede

## Stack

- **Python**: pandas, geopandas, scikit-learn, xgboost, minisom, networkx, shapely
- **Web**: Leaflet.js, Chart.js, HTML/CSS/JS vanilla
- **Deploy**: GitHub Pages (pasta `docs/`)

## Como usar

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar pipeline completo
python pipeline.py

# O resultado é gerado em docs/data/
```

## Estrutura

```
src/
  data_prep.py     # Limpeza e merge dos datasets
  network.py       # Grafo rodoviário + centralidade
  features.py      # Feature engineering
  models.py        # Treinamento ML + ensemble
  evaluation.py    # Spatial K-Fold CV
  spatial.py       # Interpolação IDW
  export.py        # GeoJSON export
docs/              # GitHub Pages (mapa interativo)
pipeline.py        # Orquestrador principal
```
