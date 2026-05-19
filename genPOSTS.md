# Ferramentas
curl -X POST http://localhost:5000/api/ferramentas \
-H "Content-Type: application/json" \
-d '{
    "nome": "Furadeira de Bancada",
    "categoria": "Furação",
    "peca_code": 100,
    "setor_codigo": 4,
    "unidade_codigo": 2,
    "quantidade": 3
}'

# Operadores
curl -X POST http://localhost:5000/api/operadores \
  -H "Content-Type: application/json" \
  -d '{
    "uid_raw": "A34F0302",
    "nome": "João Silva",
    "matricula": "TS-0042"
  }'
