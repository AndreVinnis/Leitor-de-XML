import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import estilos from "./Modal.module.css";

interface ModalProps {
  aberto: boolean;
  onFechar: () => void;
  titulo: string;
  tamanho?: "padrao" | "largo";
  /** Descrição acessível do diálogo (renderizada com DialogPrimitive.Description). */
  descricao?: ReactNode;
  children: ReactNode;
}

export function Modal({ aberto, onFechar, titulo, tamanho = "padrao", descricao, children }: ModalProps) {
  return (
    <DialogPrimitive.Root open={aberto} onOpenChange={(novoAberto) => !novoAberto && onFechar()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={estilos.overlay} />
        <DialogPrimitive.Content
          // Sem Description o Radix avisa no console; undefined explícito cala o aviso.
          {...(descricao ? {} : { "aria-describedby": undefined })}
          className={[estilos.conteudo, tamanho === "largo" ? estilos.largo : ""].filter(Boolean).join(" ")}
        >
          <DialogPrimitive.Title className={estilos.titulo}>{titulo}</DialogPrimitive.Title>
          {descricao && <DialogPrimitive.Description className={estilos.descricao}>{descricao}</DialogPrimitive.Description>}
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
