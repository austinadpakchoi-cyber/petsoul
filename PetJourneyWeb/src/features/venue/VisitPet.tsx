import { useState } from "react";
import type { PetPrivateSummary } from "@/shared/contracts";
import { PetAvatar } from "@/shared/ui";

/**
 * 到访画面里的宠物：有照片用照片；没有照片、或照片加载失败时退回全站统一的头像（live 是中性爪印，演示是授权的演示小灰猫），不留空圈。
 * portraitClass 是照片的样式（店内和户外各一套）。
 */
export function VisitPet({ pet, portraitClass }: { pet: PetPrivateSummary; portraitClass: string }) {
  const [failed, setFailed] = useState(false);
  if (pet.photo_url && !failed) return <img className={portraitClass} src={pet.photo_url} alt="" onError={() => setFailed(true)} />;
  return <PetAvatar petId={pet.pet_id} name={pet.name} species={pet.species} photoUrl={null} size={58} />;
}
