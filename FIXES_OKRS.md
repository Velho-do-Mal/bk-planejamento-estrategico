# Correções de Persistência de Dados - Módulo OKRs

## Problemas Corrigidos

### 1. ✅ Banco de Dados Efêmero em Produção (CRÍTICO)
**Arquivo**: `bk_plan/settings.py`

**Problema**: O aplicativo estava usando SQLite local em vez de PostgreSQL no Railway. Cada deploy criava um novo container com um banco de dados vazio, perdendo todos os dados anteriores.

**Solução**:
- Modificado o arquivo de configurações para verificar se `DATABASE_URL` está configurado
- Em produção (quando `ENVIRONMENT=production`), o aplicativo agora força um erro se `DATABASE_URL` não estiver configurado
- Isso garante que o PostgreSQL do Railway seja usado em produção
- Em desenvolvimento local, continua usando SQLite

**Código alterado**:
```python
# Em produção (Railway), DATABASE_URL deve estar configurado com PostgreSQL
if DATABASE_URL and DATABASE_URL.startswith(('postgres', 'postgresql')):
    DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=False)}
elif os.environ.get('ENVIRONMENT') == 'production':
    # Forçar erro se DATABASE_URL não estiver configurado em produção
    raise ValueError(
        'DATABASE_URL não configurado em produção. '
        'Configure uma instância PostgreSQL no Railway e defina DATABASE_URL nas variáveis de ambiente.'
    )
else:
    # Desenvolvimento local com SQLite
    DATABASES = {...}
```

### 2. ✅ Inconsistência de Chaves JSON
**Arquivos**: `apps/planejamento/models.py` e `apps/planejamento/views.py`

**Problema**: O código usava chaves diferentes para armazenar KPIs:
- Modelo padrão: `dados['okrs']`
- Views: `dados['s']`
- Alguns templates: `dados.okrs`

Isso causava dados perdidos quando o código procurava pela chave errada.

**Solução**:
- Padronizado o uso de `dados['s']` em todo o código
- Alterado o modelo padrão em `PlanningData.get_or_create_default()` para inicializar com `'s': []` em vez de `'okrs': []`
- Adicionada função de normalização em `get_planning()` que migra dados antigos de `'okrs'` para `'s'` automaticamente

**Código alterado em models.py**:
```python
defaults={'dados': {
    'partners': [], 'areas': [], 'swot': [], 's': [], 'actions': [],  # ✅ 's' em vez de 'okrs'
    'strategic': {...}
}}
```

**Código alterado em views.py**:
```python
def get_planning() -> dict:
    # ... código existente ...
    
    # Normalizar dados antigos: migrar 'okrs' para 's' se existir
    if "okrs" in dados and dados["okrs"]:
        if "s" not in dados or not dados["s"]:
            dados["s"] = dados["okrs"]
        # Remover chave 'okrs' antiga
        del dados["okrs"]
        obj.dados = dados
        obj.save()
    
    dados.setdefault("s", [])
    
    return dados
```

### 3. ✅ Migração de Dados Existentes
**Arquivo**: `apps/planejamento/migrations/0002_normalize_okrs_to_s.py`

**Problema**: Dados existentes no banco de dados ainda estavam usando a chave `'okrs'`.

**Solução**:
- Criada migração Django que normaliza todos os registros existentes
- A migração verifica cada registro e migra dados de `'okrs'` para `'s'` se necessário
- Executa automaticamente ao fazer deploy com `python manage.py migrate`

## Como Fazer Deploy das Correções

### Pré-requisitos no Railway:
1. **Configurar PostgreSQL**: Certifique-se de que existe uma instância PostgreSQL no Railway
2. **Definir variáveis de ambiente**:
   - `DATABASE_URL`: URL de conexão do PostgreSQL (geralmente já configurada automaticamente pelo Railway)
   - `ENVIRONMENT=production`: Para indicar que está em produção

### Passos:
1. Fazer push das alterações para o repositório Git
2. O Railway detectará as mudanças e iniciará o deploy
3. Durante o deploy, o comando `python manage.py migrate` executará automaticamente:
   - Aplicará a migração `0002_normalize_okrs_to_s.py`
   - Normalizará todos os dados existentes
4. Os dados antigos serão preservados e migrados para a nova estrutura

## Validação

Após o deploy, para validar que as correções funcionaram:

1. **Verificar banco de dados**:
   ```bash
   # No Django shell
   python manage.py shell
   from apps.planejamento.models import PlanningData
   obj = PlanningData.get_or_create_default()
   print(obj.dados.keys())  # Deve conter 's' e não 'okrs'
   ```

2. **Testar persistência**:
   - Cadastrar um novo KPI no módulo OKRs
   - Sair do sistema
   - Fazer login novamente
   - Verificar se o KPI ainda está lá
   - Fazer um deploy/redeploy
   - Verificar se o KPI foi preservado

3. **Verificar logs**:
   - Procurar por erros relacionados a `DATABASE_URL` não configurado
   - Se houver erro, significa que `DATABASE_URL` não está configurado no Railway

## Arquivos Modificados

- `bk_plan/settings.py` - Configuração de banco de dados
- `apps/planejamento/models.py` - Modelo padrão
- `apps/planejamento/views.py` - Função de normalização
- `apps/planejamento/migrations/0002_normalize_okrs_to_s.py` - Migração de dados (novo arquivo)

## Notas Importantes

- ⚠️ **Não altere o frontend**: As alterações foram feitas apenas no backend
- ✅ **Dados preservados**: Todos os dados existentes serão migrados automaticamente
- ✅ **Compatibilidade**: O código continua funcionando em desenvolvimento local com SQLite
- 🔒 **Segurança**: Em produção, o aplicativo agora força o uso de PostgreSQL, evitando perda de dados

## Suporte

Se encontrar problemas após o deploy:
1. Verifique se `DATABASE_URL` está configurado no Railway
2. Verifique os logs do Railway para mensagens de erro
3. Certifique-se de que a instância PostgreSQL está rodando
4. Execute manualmente `python manage.py migrate` se necessário
