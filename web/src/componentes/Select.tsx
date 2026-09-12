import * as SelectPrimitive from "@radix-ui/react-select";
import estilos from "./Select.module.css";

export interface OpcaoSelect<T extends string> {
  valor: T;
  rotulo: string;
}

interface SelectProps<T extends string> {
  valor: T;
  opcoes: OpcaoSelect<T>[];
  onMudar: (valor: T) => void;
  rotuloAria: string;
}

export function Select<T extends string>({ valor, opcoes, onMudar, rotuloAria }: SelectProps<T>) {
  return (
    <SelectPrimitive.Root value={valor} onValueChange={(novoValor) => onMudar(novoValor as T)}>
      <SelectPrimitive.Trigger className={estilos.gatilho} aria-label={rotuloAria}>
        <SelectPrimitive.Value />
        <SelectPrimitive.Icon className={estilos.icone}>▾</SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content className={estilos.conteudo}>
          <SelectPrimitive.Viewport>
            {opcoes.map((opcao) => (
              <SelectPrimitive.Item key={opcao.valor} value={opcao.valor} className={estilos.item}>
                <SelectPrimitive.ItemText>{opcao.rotulo}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className={estilos.indicador}>✓</SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
