## Conclusiones

| Hallazgo | Qué se decidió |
|---|---|
| Sesiones y minutos son muy asimétricos (asimetría 1,7 y 1,9) y las escalas cambian entre materias. | `log(1 + x)` en sesiones y minutos y estandarización **dentro de cada materia** (D57): cada alumno se compara con su curso. |
| Las 5 variables están muy correlacionadas: el primer componente de PCA explica el 79 % y el segundo (nota vs. actividad) otro 11 %. | El mapa de la app usa esos dos ejes. Los grupos son, sobre todo, tramos de "cuánto participa y le va". |
| k = 2 tiene el mejor silhouette pero solo separa "entran / no entran". Entre 3 y 6, silhouette, Davies-Bouldin y Calinski-Harabasz coinciden en **k = 3**. El codo no es nítido. | Se mantiene k automático entre 3 y 6 por silhouette (D57). `evaluar_k` informa también Davies-Bouldin y Calinski-Harabasz (D71). |
| Silhouette 0,41: estructura moderada; solo el 1 % de los alumnos tiene silhouette negativo. | Se explica en la app como "grupos con fronteras difusas", no como tipos cerrados. |
| Grupos con k = 3: Comprometidos (54 %), Intermitentes (33 %) y Desconectados (13 %). | Nombres por centroide (D57, D68). |
| Jerárquico (Ward) coincide bastante con K-Means (ARI 0,69), la mezcla gaussiana menos (0,51). DBSCAN encuentra un solo bloque denso más 5 % de ruido. | No hay grupos separados por zonas vacías: K-Means segmenta un continuo. Se queda K-Means (mejor silhouette, simple y estable). |
| Bootstrap: ARI medio 0,95 con k = 3; baja con k = 4 a 6 (0,76 a 0,89). | Nueva función `estabilidad()` en `src/ml_grupos.py` (D71). Los grupos de k = 3 son confiables; los de k grande, menos. |
| Validación externa: abandonó la materia el 1 % de los Comprometidos, el 22 % de los Intermitentes y el 53 % de los Desconectados; el 99 % de los Desconectados está libre. | Los grupos, armados sin mirar la condición ni el abandono, sirven para priorizar. Se usan como complemento del predictor. |
| Los atípicos (IsolationForest) son casi todos alumnos que no entraron nunca o una vez. | No se agrega una alerta de atípicos: ya los cubren "Desconectados" y las alertas de inactividad. |
