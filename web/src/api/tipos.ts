// Contratos tipados à mão -- a maioria das rotas da API não declara
// response_model (só app/api/routes_casos.py o faz), então o OpenAPI não
// tem schema de resposta para gerar isso automaticamente. Ver a seção 1.3
// do plano de migração (fora de escopo desta fase, tratar como dívida).

export interface UsuarioLogado {
  id: number;
  email: string;
  nome: string;
  role: "comum" | "administrador";
  status_cadastro: "pendente" | "aprovado" | "reprovado";
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
}

export interface LoginResposta {
  access_token: string;
  token_type: string;
}

export interface ClienteCaso {
  id: number;
  nome_cliente: string;
  identificacao_caso: string | null;
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
