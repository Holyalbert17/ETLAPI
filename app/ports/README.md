# Puertos

`BaseExtractor`, `BaseLoader` y `BaseRepository` son las interfaces que el núcleo usa
para leer un origen, persistir registros y consultar datos. El dominio no importa
drivers concretos: eso vive en `app/adapters`.
