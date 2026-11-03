---
title: "QA Preditivo: Como usar Machine Learning para antecipar bugs antes do deploy"
description: "Construí um preditor de defeitos just-in-time, treinei no requests e no Flask e avaliei do jeito que ele seria usado de verdade. Funciona. Só não do jeito que os slides de venda dizem."
publishDate: 2026-11-03
lang: pt
key: predictive-qa
tags:
  - QA
  - Machine Learning
  - CI/CD
  - Python
repo: https://github.com/douglasbonafe/predictive-qa
cover: /assets/blog/predictive-qa-pt.jpg
cover_alt: "QA Preditivo: ranqueando commits por risco de bug antes do deploy"
---

Todo time de QA com quem trabalhei tem o mesmo problema, só muda a roupa. Tem mais mudança do que atenção para revisar. Alguém sobe um PR de 400 linhas às 17h de uma quinta, duas pessoas aprovam em onze minutos, e o postmortem da semana seguinte diz "testes insuficientes", como se teste fosse tempero que você joga por cima.

QA preditivo é a ideia de gastar essa atenção melhor. Antes de um commit ir para produção, você calcula a chance de ele carregar um bug e manda os arriscados para um segundo revisor, uma suíte de testes mais longa ou um rollout mais lento. Na pesquisa o nome é predição de defeitos just-in-time (JIT), e existe desde que Mockus e Weiss fizeram isso no Bell Labs em 2000.

Tenho visto muito pitch disso ultimamente, quase sempre com um AUC de 0.85 no slide e nenhuma palavra sobre como foi medido. Então construí um do zero, rodei em dois codebases reais e medi do jeito que um time usaria. O código está aqui: [douglasbonafe/predictive-qa](https://github.com/douglasbonafe/predictive-qa).

Versão curta: funciona, é barato, e a maior parte do poder dele vem de algo que você calcula com `git diff --stat`. A versão longa é mais útil.

## As três peças

Todo preditor JIT precisa de labels, features e um modelo. O modelo é a parte menos interessante.

### Labels: quais commits foram ruins?

Você não tem uma lista de "commits que causaram bugs". Ninguém tem. O que você tem é uma lista de commits que corrigiram alguma coisa, e isso basta para andar de trás para frente.

O truque padrão é o SZZ, nome tirado de Śliwerski, Zimmermann e Zeller, que publicaram em 2005. Pegue um commit de correção. Veja as linhas que ele precisou apagar ou editar. Rode `git blame` nessas linhas na versão anterior. Quem mexeu nelas por último introduziu o bug.

```python
def _links_for_fix(repo, fix, max_files):
    code = [f for f in fix.files if f.deleted > 0 and is_code_file(f.path)]
    if not code or len(code) > max_files:   # big "fixes" are usually refactors
        return []
    parent = fix.parents[0]
    found = set()
    for f in code:
        ranges = deleted_ranges(repo, parent, fix.sha, f.path)   # git diff -U0 -w
        found.update(blame_lines(repo, parent, f.path, ranges))  # git blame -w --porcelain
    return [Link(s, fix.sha, fix.timestamp) for s in found]
```

É grosseiro. As correções são achadas por palavras-chave na mensagem do commit, então "fix typo in README" conta, e uma correção que só adiciona um null check que faltava não aponta para ninguém. Herbold e colegas auditaram isso em 2022 e descobriram que só cerca de metade dos commits que o SZZ trata como correção de bug realmente são. Essa é a qualidade de label com que a área inteira trabalha. Eu mantenho, e me lembro disso toda vez que leio os resultados.

Um detalhe que importa mais adiante: eu guardo *quando* cada commit ruim foi exposto, não só que ele foi. O timestamp da primeira correção é o que torna uma avaliação honesta possível.

### Features: como é um commit arriscado?

Usei as 14 métricas de mudança de Kamei et al. (2013), que ainda são a referência. Elas caem em cinco grupos:

- Tamanho: linhas adicionadas, linhas removidas, tamanho dos arquivos tocados.
- Difusão: por quantos arquivos, diretórios e subsistemas a mudança se espalha, e quão uniforme.
- Propósito: o próprio commit é uma correção?
- Histórico: quantos devs já mexeram nesses arquivos, quanto tempo desde a última mudança, quantas mudanças anteriores.
- Experiência: quantos commits o autor fez no total, recentemente e nesse subsistema.

Adicionei mais uma de Rahman e Devanbu (2013): o número de correções anteriores que tocaram os mesmos arquivos. Código que vive precisando de correção tende a continuar precisando.

Tudo sai de uma única passada no `git log --numstat`, do commit mais antigo para o mais novo. A linha de cada commit é escrita antes de o estado acumulado ser atualizado, então nenhum commit enxerga o próprio futuro. Tem teste para isso, porque é o tipo de bug que deixa tudo mais bonito e ninguém percebe.

### Modelo: regressão logística, na maior parte

Treinei regressão logística e gradient boosting com as features em escala log e pesos de classe balanceados. Nada exótico. A regressão logística ganhou nos dados que eu tinha, e tem uma vantagem real numa ferramenta de CI: dá para explicar o score. "Esse commit é arriscado porque adiciona muitas linhas em arquivos que precisaram de cinco correções este ano" é algo que um revisor consegue usar. "A árvore disse 0.71" não é.

## O jeito de avaliar decide tudo

É aqui que a maioria das demos desmorona.

O jeito preguiçoso é embaralhar todos os commits, dividir 70/30 e usar os labels que você tem hoje. Parece ok. Está errado duas vezes.

Primeiro, treina com o futuro. Um split aleatório coloca commits de 2024 no treino e de 2019 no teste. O modelo aprende padrões de um código que ainda nem existia quando aqueles commits de teste foram escritos. Em produção, o modelo só vai pontuar os commits de amanhã com o conhecimento de ontem.

Segundo, vaza label. Se você treina com commits de 2020 usando a saída do SZZ de hoje, alguns estão marcados como bugados por causa de correções que entraram em 2022. Em 2020, na hora do treino, não tinha como saber.

Então a avaliação do POC faz assim:

1. Folds móveis em ordem temporal. Treina nos primeiros 40% do histórico e testa nos 8% seguintes. Depois 48% e os 8% seguintes, e assim por diante, cinco vezes.
2. Labels na data. Um commit de treino só conta como bugado se a correção dele já tinha entrado até a data de corte do treino.
3. Nada de dado fresco no teste. Os 20% mais recentes do histórico nunca são testados, porque os bugs deles ainda não foram achados e quase tudo ali parece limpo.
4. Baselines. Todo modelo é comparado com "revisar os maiores commits primeiro" e "revisar os menores primeiro". Se o modelo não ganha de uma ordenação, não vai para produção.
5. Métricas de orçamento. O AUC aparece, mas o número que importa é: se o time revisa os 20% de commits mais arriscados, que fração dos ruins ele pega?

```python
for c in cutoffs:
    i, j = int(c * n), int((c + window) * n)
    train, test = df.iloc[:i], df.iloc[i:j]
    cutoff_ts = int(train["timestamp"].iloc[-1])
    y_train = labels_as_of(train, cutoff_ts)   # only fixes known at the cutoff
    y_test = y_final[i:j]                      # full hindsight for scoring
```

## Resultados no requests e no Flask

Rodei no [psf/requests](https://github.com/psf/requests) e no [pallets/flask](https://github.com/pallets/flask). As duas são bibliotecas Python maduras, bem revisadas e com histórico longo. Tirando os commits que não mexem em código (o SZZ não consegue rotulá-los, e mantê-los faz qualquer modelo parecer mais esperto), sobram 2.830 e 2.029 commits. O SZZ marcou 17,7% e 20,7% deles como causadores de bug, dentro da faixa que Kamei reportou nos projetos dele.

Médias de cinco folds móveis:

| | requests | flask |
|---|---|---|
| Ordem aleatória: bugs pegos nos 20% do topo | 19% | 22% |
| Regressão logística: bugs pegos nos 20% do topo | 34% | 41% |
| "Maior commit primeiro": bugs pegos nos 20% do topo | 34% | 49% |
| AUC, regressão logística | 0.69 | 0.73 |
| AUC, maior commit primeiro | 0.69 | 0.77 |
| AUC, regressão logística, **split embaralhado** | 0.75 | 0.81 |

Leia essa tabela duas vezes. Eu li.

**O modelo mais ou menos dobra o que você pegaria por acaso.** Revisar o quinto mais arriscado dos commits pega entre um terço e dois quintos dos ruins. Isso é real, e para uma ferramenta que custa uns segundos no CI, é uma boa troca.

**Uma baseline de uma linha faz o mesmo.** Ordenar commits por linhas alteradas empata com o modelo no requests e ganha dele no Flask. Fui ver o que sobra quando o tamanho fica constante: dentro de cada quartil de tamanho, o ranking do modelo é pouco melhor que uma moeda, e um modelo treinado sem as features de tamanho tira AUC de 0.51. Nesses dois codebases, tudo além do tamanho é quase ruído.

**O split com vazamento infla o AUC em 6 a 8 pontos.** Mesmo modelo, mesmas features, mesmos dados. Só embaralhado e com visão do futuro. 0.81 parece produto. 0.73 parece heurística. O 0.73 é o que vai se sustentar no seu pipeline.

## A armadilha de métrica que ninguém coloca no slide

Tem uma segunda família de métricas nessa literatura, chamada effort-aware. Em vez de "quantos commits ruins estão nos 20% do topo", ela pergunta "quantos commits ruins você acha lendo 20% de todas as linhas alteradas". Parece mais realista, já que commit grande custa mais para revisar.

Aí você roda. "Menor commit primeiro" acha 78% dos commits ruins no requests usando só 20% das linhas. Impressionante, até você adicionar a coluna que ninguém reporta: para chegar lá, você abriu 85% de todos os commits. Não economizou tempo de revisão. Só revisou quase tudo, numa ordem esquisita.

Yang et al. (2016) mostraram que rankers simples e não supervisionados assim ganham dos modelos supervisionados em métricas effort-aware. Huang, Xia e Lo (2017) responderam que, quando você conta quantos commits o dev precisa abrir, o quadro se inverte. Meus números reproduzem os dois artigos numa tabela só, o que é um bom lembrete de que a métrica é decisão de produto, não técnica. Escolha o orçamento que seus revisores realmente têm e meça isso.

## O que eu colocaria em produção de verdade

Não um bloqueador de merge. Lewis et al. rodaram um preditor de bugs no Google inteiro em 2013 e não encontraram mudança mensurável no comportamento dos devs. Os engenheiros ignoraram scores com os quais não sabiam o que fazer e nos quais não confiavam. Esse artigo devia ser leitura obrigatória para quem vende "AI quality gates".

O que funciona é roteamento. O POC vem com um workflow de GitHub Actions que retreina no histórico do próprio repo a cada PR (segundos para alguns milhares de commits), pontua os commits do PR e escreve uma tabela no resumo do job:

```
| Commit                         | Risk         | Lines    | Why                                              |
|--------------------------------|--------------|----------|--------------------------------------------------|
| `bfc8f983` add `versionchanged` | 0.61 (low)  | +67/-11  | lines added, author recent activity, file size   |
| `329c32b9` fix dev              | 0.45 (low)  | +33/-36  | author recent activity, lines added, prior fixes |
```

Risco alto significa duas coisas: precisa de um segundo revisor, e roda a suíte completa em vez dos smoke tests. Nunca significa "esse commit está errado". O limiar é ajustado para uns 20% dos commits passarem dele, um orçamento que o time absorve sem aprender a ignorar.

E sendo honesto: se o seu próprio relatório do `pqa evaluate` mostrar que o modelo não ganha de "maior commit primeiro", coloque a baseline em produção. É uma linha de bash, dá para explicar num postmortem, e é a maior parte do valor.

## Onde estão os ganhos de verdade

Descobrir que o tamanho domina não é falha do ML. É uma constatação sobre o que o histórico do git contém. O log sabe o tamanho de uma mudança e quem escreveu. Ele não sabe:

- quanto do código alterado está coberto por testes,
- se o CI andou instável naquele caminho na semana passada,
- quanto tempo o PR ficou em revisão e quantos comentários recebeu,
- se o autor é dono daquele módulo ou está de passagem,
- se a mudança toca um caminho quente nos traces de produção.

Esses são os sinais que eu adicionaria a seguir, e todos estão disponíveis num setup normal de empresa. O diff de cobertura sai do seu test runner. Os dados de revisão vêm da API do GitHub. A propriedade do código vem do CODEOWNERS. Os traces vêm do OpenTelemetry. O valor de um sistema de QA preditivo cresce com quanto desse contexto você alimenta nele, e com quão honestamente você mede se ele está ajudando.

## Teste no seu repositório

```bash
pip install git+https://github.com/douglasbonafe/predictive-qa
pqa mine     --repo . --out history.csv
pqa evaluate --data history.csv
pqa train    --data history.csv --model model.pkl
pqa score    --repo . --model model.pkl --range origin/main..HEAD
```

Rode o `evaluate` primeiro. Olhe a linha "biggest commit first" antes de olhar o modelo. Se você achar um codebase onde o modelo ganha com folga, quero saber.

## Referências

- Mockus, A., Weiss, D. M. *Predicting risk of software changes.* Bell Labs Technical Journal, 2000.
- Śliwerski, J., Zimmermann, T., Zeller, A. *When do changes induce fixes?* MSR 2005.
- Kamei, Y. et al. *A large-scale empirical study of just-in-time quality assurance.* IEEE TSE, 2013.
- Rahman, F., Devanbu, P. *How, and why, process metrics are better.* ICSE 2013.
- Lewis, C. et al. *Does bug prediction support human developers? Findings from a Google case study.* ICSE 2013.
- Yang, Y. et al. *Effort-aware just-in-time defect prediction: simple unsupervised models could be better than supervised models.* FSE 2016.
- Huang, Q., Xia, X., Lo, D. *Supervised vs unsupervised models: a holistic look at effort-aware just-in-time defect prediction.* ICSME 2017.
- Herbold, S. et al. *Problems with SZZ and features: an empirical study of the state of practice of defect prediction data collection.* Empirical Software Engineering, 2022.
