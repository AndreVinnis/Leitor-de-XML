// Contratos tipados à mão -- a maioria das rotas da API não declara
// response_model (só app/api/routes_casos.py o faz), então o OpenAPI não
// tem schema de resposta para gerar isso automaticamente. Ver a seção 1.3
// do plano de migração (fora de escopo desta fase, tratar como dívida).

export type RoleUsuario = "comum" | "administrador";

export type StatusCadastro = "pendente" | "aprovado" | "reprovado";

export interface UsuarioLogado {
  id: number;
  email: string;
  nome: string;
  role: RoleUsuario;
  status_cadastro: StatusCadastro;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
}

export interface ClienteCaso {
  id: number;
  nome_cliente: string;
  identificacao_caso: string | null;
  // Só dígitos, sem pontuação -- ver app/models/models.py::ClienteCaso.cnpj_cliente.
  cnpj_cliente: string | null;
  criado_em: string;
}

export interface EstatisticasDashboard {
  notas_processadas: number;
  pendentes: number;
  erros: number;
}

export type StatusNota = "pendente" | "sucesso" | "erro" | "duplicado";

export type TipoNota = "entrada" | "saida";

export interface NotaResumo {
  id: number;
  numero: string | null;
  tipo: TipoNota | null;
  emitente_nome: string | null;
  destinatario_nome: string | null;
  data_emissao: string | null;
  // Decimal serializado como string pela API -- nunca number. Formatar na
  // exibição, nunca fazer conta com esse campo direto no front.
  valor_total: string | null;
  status: StatusNota | null;
}

export interface ListaNotas {
  itens: NotaResumo[];
  total: number;
}

export interface ItemNotaDetalhe {
  id: number;
  numero_item: number | null;
  codigo_produto: string | null;
  descricao_original: string;
  ncm: string | null;
  cfop: string | null;
  unidade: string | null;
  // Decimal/quantidade serializados como string pela API -- ver NotaResumo.valor_total.
  quantidade: string | null;
  valor_unitario: string | null;
  valor_total: string | null;
  produto_canonico_id: number | null;
  produto_canonico_nome: string | null;
}

export interface NotaDetalhe {
  id: number;
  chave_acesso: string;
  tipo: TipoNota;
  numero: string | null;
  serie: string | null;
  data_emissao: string | null;
  emitente_cnpj: string | null;
  emitente_nome: string | null;
  destinatario_cnpj: string | null;
  destinatario_nome: string | null;
  valor_total: string | null;
  cliente_caso_id: number;
  status: StatusNota | null;
  arquivo_origem: string | null;
  itens: ItemNotaDetalhe[];
}

export interface UploadNotasResposta {
  status: string;
  lote_id: string;
  total_arquivos: number;
  task_ids: string[];
}

export interface ArquivoLoteProgresso {
  id: number;
  nome_arquivo: string;
  status: StatusNota | null;
  motivo_erro: string | null;
  nota_id: number | null;
}

export interface ProgressoLote {
  lote_id: string;
  total_arquivos: number;
  concluidos: number;
  com_erro: number;
  arquivos: ArquivoLoteProgresso[];
}

// -- Produtos (app/api/routes_produtos.py) --------------------------------

export type StatusRevisao = "pendente" | "confirmado" | "rejeitado";

export interface SugestaoNormalizacao {
  id: number;
  item_nota_id: number;
  descricao_original: string;
  produto_canonico_sugerido_id: number;
  nome_canonico: string;
  categoria: string | null;
  fornecedor: string | null;
  confianca: number;
  status: StatusRevisao;
  criado_em: string;
}

export interface ListaSugestoes {
  itens: SugestaoNormalizacao[];
  total: number;
}

export interface ProdutoCanonico {
  id: number;
  nome_canonico: string;
  categoria: string | null;
  itens_vinculados_count: number;
}

export interface ListaCanonicos {
  itens: ProdutoCanonico[];
  total: number;
}

export interface DisparoNormalizacao {
  status: string;
  task_id: string;
}

// app/workers/tasks.py::normalizar_produtos_pendentes -- "erro_inesperado"
// só acontece se uma exceção escapar da task (bug), não é um caminho normal.
export interface ResultadoNormalizacao {
  status: "ok" | "erro_inesperado";
  descricoes_unicas?: number;
  itens_pendentes?: number;
  produtos_canonicos_criados?: number;
  sugestoes_criadas?: number;
  motivo?: string;
}

// result.status de um AsyncResult do Celery (PENDING/STARTED/SUCCESS/FAILURE/...) --
// resultado só vem preenchido quando a task termina (result.ready()).
export interface StatusNormalizacao {
  task_id: string;
  status: string;
  resultado: ResultadoNormalizacao | null;
}

// As rotas de revisão (confirmar/rejeitar/corrigir, unitárias e em lote)
// devolvem sempre HTTP 200 -- o campo "status" do corpo é que diz se deu
// certo. Ver comentário de app/api/routes_produtos.py::_revisar.
export interface ResultadoRevisao {
  status: "ok" | "erro";
  sugestao_id?: number;
  motivo?: string;
}

export interface ResultadoRevisaoLote {
  resultados: ResultadoRevisao[];
}

export interface ItemVinculado {
  id: number;
  nota_id: number;
  nota_numero: string | null;
  tipo: TipoNota;
  fornecedor: string | null;
  data_emissao: string | null;
  descricao_original: string;
  // Decimal serializado como string pela API -- ver NotaResumo.valor_total.
  quantidade: string | null;
  unidade: string | null;
  valor_unitario: string | null;
  valor_total: string | null;
}

export interface ListaItensVinculados {
  produto_canonico: { id: number; nome_canonico: string; categoria: string | null };
  itens: ItemVinculado[];
  total: number;
}

// -- Consulta (app/api/routes_consulta.py) --------------------------------

export interface ResultadoConsulta {
  pergunta: string;
  sql_gerado: string;
  colunas: string[];
  linhas: unknown[][];
  total_linhas: number;
}

// -- Usuários / Aprovação de Cadastros (app/api/routes_usuarios.py) -------

export interface UsuarioAdmin {
  id: number;
  nome: string;
  email: string;
  role: RoleUsuario;
  status_cadastro: StatusCadastro;
  is_active: boolean;
  criado_em: string;
}

export interface ListaUsuarios {
  itens: UsuarioAdmin[];
  total: number;
}

// Aprovar/reprovar (unitário e em lote) devolvem sempre HTTP 200 -- ver
// comentário de app/api/routes_usuarios.py::_decidir_cadastro.
export interface ResultadoDecisaoCadastro {
  status: "ok" | "erro";
  usuario_id?: number;
  motivo?: string;
}

export interface ResultadoDecisaoCadastroLote {
  resultados: ResultadoDecisaoCadastro[];
}

// -- Auditoria (app/api/routes_auditoria.py) ------------------------------

export interface LogAuditoria {
  id: number;
  criado_em: string;
  usuario_nome: string;
  acao: string;
  resumo: string | null;
  pergunta_usuario: string | null;
  sql_gerado: string | null;
}

export interface ListaLogsAuditoria {
  itens: LogAuditoria[];
  total: number;
}
