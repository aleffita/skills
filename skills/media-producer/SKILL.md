---
name: media-producer
description: Produce AI-generated visual content (images and videos) using Z.AI models. Supports full production workflow with pre-production documentation, asset generation, and composition. Use when creating videos, image sequences, or complete visual productions.
license: Complete terms in LICENSE.txt
---

# Media Producer Skill

Produza conteúdo visual com IA usando modelos Z.AI. Esta skill suporta um **workflow completo de produção**:

1. **Pré-Produção**: Documento estruturado, follow-up questions, planejamento
2. **Produção**: Geração de assets (imagens, vídeos)
3. **Pós-Produção**: Composição final com FFmpeg

## Modelos Disponíveis

### Imagens (CogView-4)
| Modelo | Concurrency | Uso |
|--------|-------------|-----|
| CogView-4-250304 | 5 | Frames, storyboards, referências |

### Vídeos
| Modelo | Concurrency | Uso |
|--------|-------------|-----|
| CogVideoX-3 | 1 | Melhor qualidade, text/image/frame-transition |
| ViduQ1-text | 5 | Text-to-video, alta concorrência |
| ViduQ1-Image | 5 | Image-to-video |
| ViduQ1-Start-End | 5 | Frame transitions |
| Vidu2-* | 5 | Alternativas |

## Requisitos

- **Variável de ambiente**: `Z_AI_API_KEY` deve estar configurada
- **FFmpeg**: Necessário para composição de vídeos (install via brew/apt)

---

# Workflow

## Fase 1: Pré-Produção

**SEMPRE comece com follow-up questions para entender a visão do usuário.**

### Perguntas Essenciais
1. Qual é a visão geral do projeto?
2. Qual estilo visual? (realistic, 3D, anime, cinematic, etc.)
3. Quantas cenas aproximadamente?
4. Duração total desejada?
5. Possui referências (imagens, vídeos, artigos)?

### Criar Projeto
```bash
uv run scripts/project.py init "Nome do Projeto" --output ./my_project/ --vision "..." --style "..."
```

### Adicionar Cenas
```bash
uv run scripts/project.py add-scene --project ./my_project/ \
  --name "Intro" \
  --type text-to-video \
  --prompt "Detailed prompt here..." \
  --duration 5
```

### Adicionar Referências
```bash
uv run scripts/project.py add-reference --project ./my_project/ \
  --type url \
  --content "https://..." \
  --summary "Description of reference"
```

---

## Fase 2: Produção

### Gerar Imagens (CogView-4)

```bash
# Imagem única
uv run scripts/generate_image.py --prompt "Description" --output image.png

# Múltiplas imagens
uv run scripts/generate_image.py --prompt "Description" --output ./frames/ --count 4 --prefix frame_
```

**Parâmetros:**
- `--prompt`: Descrição textual (obrigatório)
- `--output`: Arquivo ou diretório de saída
- `--size`: Resolução (padrão: 1024x1024)
- `--count`: Número de imagens
- `--prefix`: Prefixo para múltiplas imagens

### Gerar Vídeos

```bash
# Text-to-video (melhor qualidade)
uv run scripts/generate_video.py --prompt "Description" --output video.mp4

# Text-to-video (alta concorrência)
uv run scripts/generate_video.py --model viduq1-text --prompt "Description" --output video.mp4

# Image-to-video
uv run scripts/generate_video.py --model viduq1-image \
  --prompt "Animate this scene" \
  --image-url "https://..." \
  --output video.mp4

# Frame transition
uv run scripts/generate_video.py --model viduq1-start-end \
  --prompt "Smooth transition" \
  --image-url "https://start.jpg" "https://end.jpg" \
  --output video.mp4
```

**Parâmetros:**
- `--model`: Modelo a usar (padrão: cogvideox-3)
- `--prompt`: Descrição textual (obrigatório)
- `--image-url`: URL(s) para image-to-video ou frame-transition
- `--output`: Arquivo de saída
- `--quality`: quality (padrão) ou speed
- `--size`: Resolução (padrão: 1920x1080)
- `--fps`: 30 (padrão) ou 60
- `--duration`: 5 (padrão) ou 10 segundos
- `--list-models`: Listar modelos disponíveis

### Atualizar Scene com Output
```bash
# Após gerar, atualize o scene no projeto
# (faça isso manualmente ou via edição do SQLite)
```

---

## Fase 3: Pós-Produção

### Compor Vídeos

```bash
# Concatenar vídeos do projeto
uv run scripts/compose.py --project ./my_project/ --output final.mp4

# Concatenar vídeos específicos
uv run scripts/compose.py --inputs scene1.mp4 scene2.mp4 --output final.mp4

# Com transição
uv run scripts/compose.py --inputs *.mp4 --output final.mp4 --transition fade --transition-duration 0.5

# Com título
uv run scripts/compose.py --inputs video.mp4 --output final.mp4 --title "My Video" --title-duration 3
```

---

## Workflow Completo (Exemplo)

```
Usuário: "Quero criar um vídeo de 15s sobre borboletas com 3 cenas"

1. Follow-up questions:
   - Estilo visual? → "Documentary, realistic"
   - Cenas? → "1. Borboleta na flor, 2. Voo, 3. Pousando"
   - Referências? → [links]

2. Criar projeto:
   uv run scripts/project.py init "Borboletas" --output ./borboletas/

3. Adicionar cenas:
   uv run scripts/project.py add-scene --project ./borboletas/ --name "Flor" --type text-to-video --prompt "..." --duration 5
   uv run scripts/project.py add-scene --project ./borboletas/ --name "Voo" --type text-to-video --prompt "..." --duration 5
   uv run scripts/project.py add-scene --project ./borboletas/ --name "Pouso" --type text-to-video --prompt "..." --duration 5

4. Gerar vídeos:
   uv run scripts/generate_video.py --prompt "..." --output ./borboletas/assets/scene1.mp4
   uv run scripts/generate_video.py --prompt "..." --output ./borboletas/assets/scene2.mp4
   uv run scripts/generate_video.py --prompt "..." --output ./borboletas/assets/scene3.mp4

5. Compor final:
   uv run scripts/compose.py --project ./borboletas/ --output ./borboletas/final.mp4

6. Entregar: ./borboletas/final.mp4
```

---

## Estratégias de Modelo

| Cenário | Modelo Recomendado | Motivo |
|---------|-------------------|--------|
| Qualidade máxima | CogVideoX-3 | Melhor output |
| Múltiplos vídeos paralelos | ViduQ1-* | Concurrency 5 |
| Animação de imagem | ViduQ1-Image | Especializado |
| Transição de frames | ViduQ1-Start-End | Especializado |

**Nota**: CogVideoX-3 tem concurrency=1, então se você precisa gerar múltiplos vídeos, use ViduQ1 ou faça sequencialmente.

---

## Dicas de Prompts

Para melhores resultados, inclua:
- **Movimento**: "flowing", "swaying", "walking", "zooming"
- **Câmera**: "slow pan", "tracking shot", "zoom in"
- **Atmosfera**: "cinematic", "dreamy", "dramatic lighting"
- **Detalhes**: Especifique cores, texturas, ambiente

**Exemplos:**
```
"A monarch butterfly resting on a purple lavender flower, wings slowly opening and closing, morning dew drops, soft golden hour lighting, shallow depth of field, cinematic macro shot"

"A butterfly flying through a misty forest, sunlight filtering through leaves, tracking shot following the butterfly, dreamy atmosphere, slow motion"
```

---

## Templates

O template de documento de produção está disponível em:
`templates/production_doc.md`

Use como base para estruturar projetos complexos.

---

## Integração com Outras Skills

- **zai-cli**: Análise de imagens/vídeos, web search para referências
- **mcp-builder**: Criar MCP servers para orquestração avançada

---

## Scripts Disponíveis

| Script | Função |
|--------|--------|
| `project.py` | Gerenciar projetos (init, status, scenes, assets) |
| `generate_image.py` | Gerar imagens com CogView-4 |
| `generate_video.py` | Gerar vídeos com CogVideoX-3 / Vidu |
| `retrieve_result.py` | Buscar resultado de task assíncrona |
| `compose.py` | Compor vídeos com FFmpeg |

---

## Notas Técnicas

- Geração de vídeo é assíncrona - scripts fazem polling
- Tempo típico: 30-120 segundos por vídeo
- Formato de saída: MP4 (H.264)
- Áudio é gerado automaticamente pelos modelos de vídeo
- SQLite para persistência de projetos
