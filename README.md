# Monte Senário

App para consultar os roteiros litúrgicos (leituras + orações) das missas,
alimentado automaticamente pela Liturgia Diária (fonte principal: CNBB;
fonte alternativa: Nova Aliança) e guardado numa planilha Google Sheets.

## Estrutura

- `prefacios_drive.py` — lista e baixa os prefácios que você for subindo
  em 002_Liturgia São Peregrino / Orações Eucarísticas no Google Drive
  (mesma Service Account do Sheets, escopo "drive" já incluso). Usado
  pela tela "Prefácio antes da Oração Eucarística" no `app.py`, que
  deixa escolher qual prefácio entra no roteiro de cada data e grava a
  escolha na planilha (colunas PREFACIO_NOME / PREFACIO_TEXTO).
- `scraper.py` — busca e extrai o texto de uma data específica, combinando
  duas fontes:
  - **CNBB** — fonte **principal das leituras**. Testada com um exemplo
    real (18/09/2026). A página `liturgiadiaria.edicoescnbb.com.br` é só
    a casca (Next.js); os dados de verdade vêm de uma API JSON separada
    (achada inspecionando o DevTools → aba Network):
    `https://api-liturgia.edicoescnbb.com.br/contents/in/date/{AAAA-MM-DD}`.
    Não precisa de Playwright — um `requests.get()` simples resolve. Essa
    API só cobre a Liturgia da Palavra (leituras/salmo/evangelho); não
    tem Antífona de Entrada nem Coleta.
  - **Nova Aliança** (`novaalianca.com.br`) — única fonte de Antífona de
    Entrada e Coleta, por isso é consultada **sempre**, mesmo quando a
    CNBB responde bem. Também serve de fallback das leituras se a CNBB
    falhar (`extrair_liturgia_do_dia()` combina as duas automaticamente).
  Rode `python scraper.py` para testar a extração do dia de hoje sem
  precisar da planilha — o resultado mostra qual fonte deu as leituras e
  qual deu a Antífona/Coleta.
- `sheets_sync.py` — grava os dados extraídos numa aba `Liturgia_Diaria`
  da planilha, sem duplicar datas já existentes.
- `osm_proprio.py` — calendário fixo do Próprio dos Santos da Ordem dos
  Servos de Maria (servidimaria.net). Para as datas ali listadas, os PDFs
  trazem o formulário COMPLETO (Coleta, Prefácio, Oferendas, Comunhão,
  Bênção Solene) — cobrindo a lacuna que novaalianca.com.br deixa. Só
  funciona nessas datas fixas; nos demais dias a lacuna permanece.
- `app.py` — app Streamlit com duas abas: **Consultar** (ver o roteiro de
  uma data) e **Atualizar base (ADM)** (roda o scraper para um intervalo
  de datas e grava na planilha).

## Configuração

1. Crie a planilha no Google Sheets (pode ser em branco — a aba
   `Liturgia_Diaria` é criada automaticamente na primeira sincronização).
2. Reaproveite a Service Account já usada no projeto Leitores Peregrinos
   (ou crie uma nova) e compartilhe a planilha com o e-mail dela.
3. No Streamlit Community Cloud, em Settings → Secrets, adicione:
   ```toml
   ID_PLANILHA = "id-da-planilha-aqui"

   [gcp_service_account]
   type = "service_account"
   project_id = "..."
   private_key_id = "..."
   private_key = "..."
   client_email = "..."
   client_id = "..."
   # (demais campos do JSON da Service Account)
   ```
4. `pip install -r requirements.txt`
5. `streamlit run app.py`

## Pontos em aberto para os próximos passos

- **[RESOLVIDO] `extrair_liturgia_cnbb()` validada com exemplos reais** —
  achamos a API JSON real por trás do site (`api-liturgia.edicoescnbb.com.br`,
  descoberta via DevTools → Network), testada com o retorno de 18/09/2026
  (dia comum, sem 2ª leitura) e 20/09/2026 (domingo, com 2ª leitura — a
  referência da 2ª leitura vem certa; ver bug abaixo). No caminho, achei
  e corrigi dois bugs reais na extração: (1) a regex de "EVANGELHO" batia
  por engano dentro de "Aclamação ao Evangelho" e comia aquele bloco
  inteiro; (2) a CNBB embute uma `<div style="display: none;">` com
  metadados internos logo antes de "SEGUNDA LEITURA", que vazava pro
  fim do `salmo_texto` (BeautifulSoup não sabe que está oculta — corrigido
  removendo elementos com `display: none` antes de extrair o texto).
  Ainda não testado: uma data inexistente (confirmar que a API realmente
  retorna 404 e não outra coisa).
- **[A VERIFICAR] Datas muito no futuro não existem ainda na fonte** —
  novaalianca.com.br só publica a liturgia perto do dia (confirmado:
  em 18/09/2026 o site ainda não tinha 29/11/2026 publicado). O
  `scraper.py` já trata isso: em vez de sumir com o dia, grava uma
  linha com `LEITURAS_CONFIRMADAS = NÃO` e um aviso em `AVISO_FONTE`,
  que o `app.py` exibe em destaque na consulta. `sincronizar_intervalo()`
  retenta automaticamente essas datas pendentes nas próximas
  sincronizações, e substitui a linha assim que a fonte publicar — sem
  duplicar. **Falta verificar**: com quantos dias de antecedência o site
  costuma publicar (para saber quando reagendar a sincronização de cada
  data pendente), e se vale a pena um fallback automático usando a
  atribuição fixa do Lecionário para domingos/solenidades (que não
  mudam de ano a ano dentro do mesmo ciclo A/B/C) enquanto a fonte não
  publica.
- **Validar o parser contra casos reais**: o `scraper.py` foi escrito a
  partir da estrutura observada numa página de exemplo (domingo comum).
  Vale testar contra uma solenidade, uma memória facultativa e um dia sem
  2ª leitura antes de rodar em produção — os rótulos podem variar levemente.
  (Já testado com sucesso contra 17/09 — dia comum — e 20/09 — domingo
  com Glória e 2ª Leitura.)
- **Definir o que fazer com o campo "Palavra de Vida"** (reflexão do dia):
  hoje o scraper ignora esse trecho; se for útil para o roteiro, dá para
  adicionar como mais um campo.
- **Reaproveitar a exportação em PDF/PPTX** que já existe no projeto
  Leitores Peregrinos, para gerar o roteiro impresso da missa.
- **Agendamento automático**: hoje a atualização é manual (botão no app).
  Se preferir, dá para automatizar com um cron/GitHub Action chamando
  `sheets_sync.py` diariamente.
- **Lacuna: Oração sobre as Oferendas / Oração depois da Comunhão** —
  novaalianca.com.br não publica essas duas orações. `osm_proprio.py`
  resolve automaticamente nas datas fixas da OSM (ver tabela no arquivo);
  para o restante do ano, a fonte é completar manualmente pela tela
  "Completar Oferendas/Comunhão" do app.py (copiando do app iLiturgia,
  que você já assina).
- **Orações Eucarísticas e Prefácios**: `oracoes_eucaristicas.py` tem o
  texto integral de I, II e III (fonte: comshalom.org); falta a IV, sem
  fonte gratuita completa localizada. `prefacios.py` é um esqueleto para
  os ~56 prefácios do Missal — sendo preenchido aos poucos a partir dos
  arquivos que você está subindo em 002_Liturgia São Peregrino/Orações
  Eucarísticas no Google Drive (ex.: Prefácio do Advento I já
  confirmado e usado na simulação de 29/11/2026).
