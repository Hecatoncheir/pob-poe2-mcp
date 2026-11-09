local granted = {}

function granted.scope(build, group)
	if not group.source or group.source == "" then return nil end
	if group.noSupports or not group.gemList[1] then return "none" end
	local skills = build.skillsTab
	if skills.skillSets[skills.activeSkillSetId].removedSocketGroupList then return "skill" end
	return group.sourceItem and group.slot and "slot" or "none"
end

function granted.isSlotGroup(group)
	if group.source or not group.slot or not group.enabled then return false end
	for _, gem in ipairs(group.gemList) do
		if not (gem.gemData and gem.gemData.grantedEffect.support) then return false end
	end
	return true
end

function granted.slotGroup(build, slot)
	for index, group in ipairs(build.skillsTab.socketGroupList) do
		if group.slot == slot and granted.isSlotGroup(group) then return group, index end
	end
end

function granted.gems(build, group)
	if granted.scope(build, group) ~= "slot" then return group.gemList end
	local container = granted.slotGroup(build, group.slot)
	if not container then return group.gemList end
	local gems = { group.gemList[1] }
	for _, gem in ipairs(container.gemList) do gems[#gems + 1] = gem end
	return gems
end

function granted.canSupport(group, effect)
	if group.noSupports then return false end
	for _, skill in ipairs(group.displaySkillList or {}) do
		if calcLib.canGrantedEffectSupportActiveSkill(effect, skill) then return true end
	end
	return false
end

return granted
