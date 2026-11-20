## Conclusiones

| Hallazgo | Qué se decidió |
|---|---|
| Con 8 a 14 días sin entrar, el 83 % todavía vuelve; con 29 o más, solo el 30 %. "Dejar de entrar dos semanas" no es abandonar. | El objetivo es el desenlace: no vuelve a entrar ni a rendir hasta el último dato (D67), con 28 días de seguimiento como mínimo. |
| 8.108 casos de 228 alumnos, 9,6 % abandona; el mismo alumno aparece en muchas fotos. | Métricas para clases desbalanceadas (AUC-PR, precisión, recall) y particiones **por alumno** (hold-out 25 % y `GroupKFold`). |
| Las variables cortadas en la fecha de la foto dan exactamente igual que con todos los datos; con etiquetas mezcladas el AUC cae a 0,5. | No hay fuga de información. |
| Hay variables muy correlacionadas (días activos y sesiones, ρ 0,95; nota y % rendido, 0,94). | Se dejan: los árboles las toleran y la importancia por permutación se lee en grupo. |
| La regla "más de 7 días sin entrar" ya tiene AUC 0,85. "Días sin entrar" es la señal dominante. | La regla es la línea de base que el modelo tiene que superar. |
| 9 modelos: los mejores (gradient boosting, logística, random forest, red neuronal) quedan a menos de 0,04 de AUC-PR entre sí, con un desvío de ±0,13 entre particiones. SVM y random forest sobreajustan. | Con una sola cursada no se puede distinguir con seguridad entre los mejores; se priorizan los interpretables y estables. |
| En la búsqueda de hiperparámetros ganan los modelos más regularizados (profundidad 2, `learning_rate` 0,02, hojas de 200). Los profundos llegan a 1 en entrenamiento y bajan en validación. | **D70**: nuevos hiperparámetros del gradient boosting en `src/ml_abandono.py` (costo cada 100: 28,0 → 27,0 en validación temporal y 27,3 → 26,0 en prueba). |
| La logística gana en validación cruzada común (23,3) pero se desploma en la temporal (37,8): extrapola mal a fechas posteriores. | Se elige el modelo por **validación temporal** (D67). Hoy gana el gradient boosting con restricciones monótonas. |
| El umbral por F1 (0,32) marcaría al 7 % y detectaría al 46 % de los que abandonan; con costo 5:1 (0,12) se marca al 18 % y se detecta al 73 %. | Umbral por costo (no perder a quien abandona pesa 5 veces más que un aviso de más). |
| En prueba, el modelo cuesta 26,0 cada 100 casos contra 27,0 de la regla: 100 falsas alarmas menos y 16 abandonos más sin detectar. La probabilidad está razonablemente calibrada (Brier 0,077 contra 0,118 del trivial). | El modelo mejora a la regla **poco**: sobre todo baja las falsas alarmas. En la app se muestra la comparación con la regla. |
| Casi todo el acierto está en los "alejados" (14+ días sin entrar). Entre quienes siguen cursando detecta solo al 30 % de los que después abandonan. | Se explica en la página del predictor: sin un hueco de actividad casi no hay señal. |
| Con cursadas sintéticas de abandono brusco, la regla resulta más robusta que el modelo; con pausas, empatan. | El modelo está ajustado a esta cohorte; con datos de más cursadas habría que reentrenar y volver a comparar. |

**Lectura honesta para el informe:** el predictor ordena bien a los alumnos (AUC ~0,89) y le gana por poco a la
regla de los 7 días, sobre todo en precisión. Su valor está en dar una probabilidad por alumno, explicar los motivos
y no marcar a quienes suelen hacer pausas largas. No es mucho mejor que mirar los días sin entrar, y con una sola
cursada no se puede asegurar que generalice a otra cohorte.
